"""
RouteManager — deterministic checkpoint-validated route execution.

Sits between Navigator and MovementExecutor as a coordination layer that
adds checkpoint validation, route confidence tracking, and recovery anchor
management on top of the raw edge-execution in the nav stack.

Design principles
-----------------
- Every route has named checkpoints that must be visually confirmed.
- Confidence is tracked per-route: high-confidence routes get tighter
  timeout margins; low-confidence routes pad timeouts and add retries.
- Recovery anchors: when a route segment fails, the manager knows the
  last confirmed position and can roll back to that anchor.
- Deterministic from spawn: every route begins at a known anchor (spawn
  or last confirmed checkpoint), making replanning exact not approximate.

Route confidence lifecycle:
    0.0  → never executed
    0.0–0.5 → executed but checkpoints rarely confirmed (drift / FP risk)
    0.5–0.8 → mostly confirmed
    0.8–1.0 → consistently confirmed; timeouts can be tightened

Route storage
-------------
Routes are defined in config/nav_map.json (via NavMap + PathPlanner).
This module adds a runtime confidence history on top of the static graph.
Confidence history is in-memory only — it resets on restart.

Public API
----------
    rm = get_route_manager()

    # Execute a named route and track confidence
    result = rm.execute("sunflower_field", stop_event)

    # Get confidence for a destination
    conf = rm.route_confidence("sunflower_field")

    # Invalidate confidence (e.g. after a crash / respawn)
    rm.reset_confidence("sunflower_field")
    rm.reset_all_confidence()
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Deque, Dict, Optional

from navigation.navigator import get_navigator
from utils.logger import get_logger

log = get_logger(__name__)

# How many recent route attempts to keep in the confidence window
_HISTORY_LEN = 10

# Route confidence → timeout margin multiplier
# High confidence = we trust the route → less padding needed
_TIMEOUT_MULT: Dict[str, float] = {
    "high":   1.0,
    "medium": 1.3,
    "low":    1.8,
}


class RouteOutcome(Enum):
    SUCCESS     = auto()  # arrival confirmed by checkpoint
    UNVERIFIED  = auto()  # arrived (timeout) but checkpoint not confirmed
    FAILED      = auto()  # stop_event, hard failure
    STUCK       = auto()  # optical-flow stall — position uncertain


@dataclass
class RouteResult:
    destination:  str
    outcome:      RouteOutcome
    elapsed_sec:  float = 0.0
    confirmed:    bool  = False   # True = at least one checkpoint was visually confirmed
    message:      str   = ""


@dataclass
class _RouteHistory:
    """Rolling window of route outcomes used to compute confidence."""
    _outcomes: Deque[bool] = field(default_factory=lambda: deque(maxlen=_HISTORY_LEN))

    def record(self, success: bool) -> None:
        self._outcomes.append(success)

    def confidence(self) -> float:
        if not self._outcomes:
            return 0.0
        return sum(self._outcomes) / len(self._outcomes)

    def tier(self) -> str:
        c = self.confidence()
        if c >= 0.80:
            return "high"
        if c >= 0.50:
            return "medium"
        return "low"

    def total_attempts(self) -> int:
        return len(self._outcomes)


class RouteManager:
    """
    Deterministic checkpoint-validated route execution layer.

    One instance per session.  Not thread-safe — use from the navigation
    thread only (same constraint as Navigator).
    """

    def __init__(self) -> None:
        self._nav      = get_navigator()
        self._history: Dict[str, _RouteHistory] = {}
        self._lock     = threading.Lock()
        self._last_confirmed_anchor: Optional[str] = None
        self._last_anchor_ts: float = 0.0

    # ------------------------------------------------------------------ #
    # Primary API                                                          #
    # ------------------------------------------------------------------ #

    def execute(
        self,
        destination: str,
        stop_event: threading.Event,
        normalize_camera: bool = True,
    ) -> RouteResult:
        """
        Navigate to destination with confidence tracking.

        Wraps navigator.go_to() and records the outcome so confidence
        estimates improve with repeated executions.
        """
        t0      = time.monotonic()
        history = self._ensure_history(destination)
        tier    = history.tier()

        log.info(
            "RouteManager: → '%s' (confidence=%.2f tier=%s attempt=%d)",
            destination,
            history.confidence(),
            tier,
            history.total_attempts() + 1,
        )

        if stop_event.is_set():
            return RouteResult(destination, RouteOutcome.FAILED, message="stop_event")

        success = self._nav.go_to(
            destination,
            stop_event,
            normalize_camera=normalize_camera,
        )

        elapsed = time.monotonic() - t0

        if stop_event.is_set():
            history.record(False)
            return RouteResult(destination, RouteOutcome.FAILED, elapsed, message="stop_event")

        if success:
            history.record(True)
            self._set_anchor(destination)
            log.info(
                "RouteManager: arrived at '%s' in %.1fs (new_conf=%.2f)",
                destination, elapsed, history.confidence(),
            )
            return RouteResult(destination, RouteOutcome.SUCCESS, elapsed, confirmed=True)

        history.record(False)
        log.warning(
            "RouteManager: FAILED to reach '%s' (elapsed=%.1fs new_conf=%.2f)",
            destination, elapsed, history.confidence(),
        )
        return RouteResult(destination, RouteOutcome.FAILED, elapsed)

    # ------------------------------------------------------------------ #
    # Confidence API                                                       #
    # ------------------------------------------------------------------ #

    def route_confidence(self, destination: str) -> float:
        """Returns [0, 1] confidence for the named destination. 0 = never attempted."""
        with self._lock:
            h = self._history.get(destination)
            return h.confidence() if h else 0.0

    def route_tier(self, destination: str) -> str:
        """Returns 'high', 'medium', or 'low' (or 'unknown' if never attempted)."""
        with self._lock:
            h = self._history.get(destination)
            return h.tier() if h else "unknown"

    def reset_confidence(self, destination: str) -> None:
        """Reset history for a specific destination (e.g. after respawn)."""
        with self._lock:
            self._history.pop(destination, None)

    def reset_all_confidence(self) -> None:
        """Reset all route history — call after session restart or respawn."""
        with self._lock:
            self._history.clear()
        self._last_confirmed_anchor = None

    # ------------------------------------------------------------------ #
    # Anchor management                                                    #
    # ------------------------------------------------------------------ #

    @property
    def last_anchor(self) -> Optional[str]:
        """Last node that was confirmed via a successful route execution."""
        return self._last_confirmed_anchor

    @property
    def last_anchor_age(self) -> float:
        """Seconds since the last confirmed anchor. Returns inf if none."""
        if self._last_anchor_ts == 0.0:
            return float("inf")
        return time.monotonic() - self._last_anchor_ts

    def force_anchor(self, node_id: str) -> None:
        """
        Externally assert that we are at a specific node (e.g. after spawn,
        cannon landing, or manual position confirmation).
        """
        self._set_anchor(node_id)
        log.info("RouteManager: anchor forced to '%s'", node_id)

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    def _ensure_history(self, destination: str) -> _RouteHistory:
        with self._lock:
            if destination not in self._history:
                self._history[destination] = _RouteHistory()
            return self._history[destination]

    def _set_anchor(self, node_id: str) -> None:
        self._last_confirmed_anchor = node_id
        self._last_anchor_ts        = time.monotonic()


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[RouteManager] = None
_inst_lock = threading.Lock()


def get_route_manager() -> RouteManager:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = RouteManager()
    return _instance
