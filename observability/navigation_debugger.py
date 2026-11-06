"""
NavigationDebugger — structured navigation state snapshot for debugging.

NavigationSnapshot is split into three explicit sections so that consumers
(logging, UI, screenshots) can read only the data they need without
receiving a flat bag of mixed signals:

  RAW    RawNavigationState     — sensor/belief data as measured
  DERIVED DerivedNavigationState — computed decisions and health scores
  HISTORY NavigationEventHistory — discrete events (recoveries, transitions)

Public API:
    nd = get_navigation_debugger()
    snap = nd.snapshot()
    nd.log_snapshot()          # capture + log in one call
    nd.log_snapshot(snap, level=logging.WARNING)
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from navigation.anchor_registry import get_anchor_registry
from navigation.camera_state import get_camera_state_manager
from navigation.route_telemetry import get_route_telemetry
from world_model.localization_state import get_localization_tracker, PositionConfidence
from utils.logger import get_logger

log = get_logger(__name__)


# ── Section 1: Raw sensor / belief data ───────────────────────────────────────

@dataclass
class RawNavigationState:
    """
    Unprocessed measurements and belief values as reported by subsystems.

    This is what the sensors see — before arbitration decisions are made.
    Use this section for diagnosing sensor accuracy and belief convergence.
    """
    # Localization belief
    anchor_beliefs:          Dict[str, float]  # anchor_id → smoothed confidence
    dominant_anchor:         Optional[str]
    dominant_confidence:     float
    dominant_persistence_sec: float
    candidate_anchor:        Optional[str]     # anchor building toward dominance
    last_confirmed_anchor:   Optional[str]
    anchor_age_sec:          float             # seconds since last confirmation

    # Drift and heading
    drift_score:             float             # accumulated positional uncertainty
    heading_deg:             float
    heading_uncertainty:     float
    heading_confidence:      float
    camera_ready:            bool

    # Failure count
    consecutive_failures:    int


# ── Section 2: Derived decisions and computed scores ──────────────────────────

@dataclass
class DerivedNavigationState:
    """
    Computed signals and arbiter decisions derived from raw data.

    This is what the arbiters decided — after resolving conflicts.
    Use this section for diagnosing decision quality and routing logic.
    """
    # Localization
    confidence_tier:     str             # HIGH / MEDIUM / LOW / LOST
    localization_stable: bool            # hysteresis gate: stable = safe to navigate
    hysteresis_state:    str             # "stable" / "transitioning"
    active_route:        Optional[str]

    # Health
    navigation_health:   float           # [0, 1] composite score
    health_tier:         str             # HEALTHY / WARNING / CRITICAL / EMERGENCY

    # Edge scores (keys with ≥3 attempts)
    edge_scores:         Dict[str, float]  # edge_key → reliability [0,1]

    # FSM
    fsm_state:           str
    validation_frames:   int


# ── Section 3: Discrete event log ─────────────────────────────────────────────

@dataclass
class NavigationEventHistory:
    """
    Ordered record of discrete navigation events this session.

    Use this section for postmortem analysis and spotting recurring failures.
    """
    # Recovery events: "LEVEL_NAME@timestamp"
    recovery_events:     List[str]  = field(default_factory=list)
    session_recovery_count: int     = 0

    # Problem segments: edge keys with poor success rate
    problem_segments:    List[str]  = field(default_factory=list)

    # Active route telemetry stats
    active_route_stats:  Dict[str, float] = field(default_factory=dict)


# ── Top-level container ────────────────────────────────────────────────────────

@dataclass
class NavigationSnapshot:
    """
    Structured point-in-time navigation runtime snapshot.

    Three sections partition signals by source and purpose:
      .raw     — sensor/belief measurements
      .derived — arbiter decisions and computed health
      .history — discrete session events
    """
    timestamp:  float
    raw:        RawNavigationState
    derived:    DerivedNavigationState
    history:    NavigationEventHistory
    snapshot_elapsed_ms: float = 0.0

    @property
    def is_healthy(self) -> bool:
        return (
            self.derived.confidence_tier in ("HIGH", "MEDIUM")
            and self.raw.drift_score < 0.5
            and self.raw.consecutive_failures < 3
            and self.derived.navigation_health >= 0.50
        )

    def summary_line(self) -> str:
        """One-line human-readable summary."""
        return (
            f"anchor='{self.raw.dominant_anchor or '?'}' "
            f"conf={self.raw.dominant_confidence:.2f}({self.derived.confidence_tier}) "
            f"health={self.derived.navigation_health:.2f}({self.derived.health_tier}) "
            f"drift={self.raw.drift_score:.2f} "
            f"hdg={self.raw.heading_deg:.1f}°±{self.raw.heading_uncertainty:.1f}° "
            f"age={self.raw.anchor_age_sec:.0f}s "
            f"stable={self.derived.localization_stable} "
            f"fsm={self.derived.fsm_state or '-'} "
            f"fails={self.raw.consecutive_failures}"
        )

    def to_dict(self) -> dict:
        return asdict(self)


class NavigationDebugger:
    """
    Structured snapshot collector for navigation runtime state.

    Thread-safe: snapshot() reads from thread-safe singletons.
    """

    def __init__(self) -> None:
        self._registry  = get_anchor_registry()
        self._csm       = get_camera_state_manager()
        self._telemetry = get_route_telemetry()
        self._tracker   = get_localization_tracker()

        # Mutable tracking state (updated by Navigator/FSM callbacks)
        self._recovery_count: int       = 0
        self._recovery_history: List[str] = []
        self._fsm_state: str            = ""
        self._validation_frames: int    = 0
        self._health: float             = 1.0
        self._health_tier: str          = "HEALTHY"

    # ------------------------------------------------------------------ #
    # Snapshot                                                            #
    # ------------------------------------------------------------------ #

    def snapshot(self) -> NavigationSnapshot:
        """Collect a complete structured navigation state snapshot."""
        t0    = time.monotonic()
        state = self._tracker.state

        tier_map = {
            PositionConfidence.HIGH:   "HIGH",
            PositionConfidence.MEDIUM: "MEDIUM",
            PositionConfidence.LOW:    "LOW",
            PositionConfidence.LOST:   "LOST",
        }

        # ── Raw section ──────────────────────────────────────────────────
        anchor_beliefs: Dict[str, float] = {}
        dominant_anchor = None
        dominant_confidence = round(state.confidence, 3)
        dominant_persistence = 0.0
        candidate_anchor = None
        loc_stable = False

        try:
            from world_model.localization_engine import get_localization_engine
            eng = get_localization_engine()
            eng_state = eng.state
            anchor_beliefs = {
                aid: round(b.confidence, 3)
                for aid, b in eng_state.anchor_beliefs.items()
                if b.confidence > 0.10
            }
            dominant_anchor = eng_state.dominant_anchor
            dominant_confidence = round(eng_state.dominant_confidence, 3)
            if dominant_anchor and dominant_anchor in eng_state.anchor_beliefs:
                dominant_persistence = eng_state.anchor_beliefs[dominant_anchor].persistence_sec
            candidate_anchor = eng_state.candidate_anchor
            loc_stable = eng_state.localization_stable
        except Exception:
            dominant_anchor = state.probable_anchor

        raw = RawNavigationState(
            anchor_beliefs           = anchor_beliefs,
            dominant_anchor          = dominant_anchor,
            dominant_confidence      = dominant_confidence,
            dominant_persistence_sec = round(dominant_persistence, 1),
            candidate_anchor         = candidate_anchor,
            last_confirmed_anchor    = state.last_confirmed_anchor,
            anchor_age_sec           = round(state.anchor_age, 1),
            drift_score              = round(state.drift_score, 3),
            heading_deg              = round(self._csm.heading, 1),
            heading_uncertainty      = round(self._csm.heading_uncertainty, 1),
            heading_confidence       = round(state.heading_confidence, 3),
            camera_ready             = self._csm.is_traversal_ready,
            consecutive_failures     = state.consecutive_failures,
        )

        # ── Derived section ──────────────────────────────────────────────
        edge_scores: Dict[str, float] = {}
        try:
            from navigation.route_graph import get_route_graph
            rg = get_route_graph()
            for key, score in rg.all_scores().items():
                if score.attempt_count >= 3:
                    edge_scores[key] = round(score.reliability, 3)
        except Exception:
            pass

        derived = DerivedNavigationState(
            confidence_tier     = tier_map.get(state.tier, "?"),
            localization_stable = loc_stable,
            hysteresis_state    = "transitioning" if candidate_anchor else "stable",
            active_route        = state.active_route,
            navigation_health   = round(self._health, 3),
            health_tier         = self._health_tier,
            edge_scores         = edge_scores,
            fsm_state           = self._fsm_state,
            validation_frames   = self._validation_frames,
        )

        # ── History section ──────────────────────────────────────────────
        active_stats: Dict[str, float] = {}
        if state.active_route and state.last_confirmed_anchor:
            segment_key = f"{state.last_confirmed_anchor}→{state.active_route}"
            s = self._telemetry.stats(segment_key)
            if s:
                active_stats = {
                    "success_rate":  s.success_rate,
                    "mean_elapsed":  s.mean_elapsed,
                    "recovery_rate": s.recovery_rate,
                }

        problems = list(self._telemetry.problem_segments(threshold=0.60).keys())

        history = NavigationEventHistory(
            recovery_events       = list(self._recovery_history[-10:]),
            session_recovery_count= self._recovery_count,
            problem_segments      = problems,
            active_route_stats    = active_stats,
        )

        elapsed_ms = (time.monotonic() - t0) * 1000

        return NavigationSnapshot(
            timestamp           = t0,
            raw                 = raw,
            derived             = derived,
            history             = history,
            snapshot_elapsed_ms = round(elapsed_ms, 2),
        )

    # ------------------------------------------------------------------ #
    # Logging                                                             #
    # ------------------------------------------------------------------ #

    def log_snapshot(
        self,
        snap: Optional[NavigationSnapshot] = None,
        level: int = logging.DEBUG,
    ) -> NavigationSnapshot:
        """Capture snapshot (if not provided) and log it."""
        if snap is None:
            snap = self.snapshot()
        log.log(level, "NavDebug: %s", snap.summary_line())
        if snap.history.problem_segments:
            log.log(level, "NavDebug: problem_segments=%s", snap.history.problem_segments)
        if snap.history.recovery_events:
            log.log(level, "NavDebug: recent_recoveries=%s", snap.history.recovery_events[-3:])
        return snap

    # ------------------------------------------------------------------ #
    # State tracking callbacks (called by Navigator / RouteFSM)          #
    # ------------------------------------------------------------------ #

    # Maximum entries kept in _recovery_history to prevent unbounded growth
    # during long runs. Snapshot consumers only read the last 10 entries anyway.
    _MAX_HISTORY = 50

    def increment_recovery(self, level_name: str = "") -> None:
        """Call whenever RecoveryManager attempts a recovery."""
        self._recovery_count += 1
        if level_name:
            self._recovery_history.append(f"{level_name}@{time.monotonic():.1f}")
            if len(self._recovery_history) > self._MAX_HISTORY:
                # Keep the most recent half — preserves recent context while
                # bounding memory regardless of session length.
                self._recovery_history = self._recovery_history[-(self._MAX_HISTORY // 2):]

    def set_fsm_state(self, state: str) -> None:
        self._fsm_state = state

    def set_validation_frames(self, n: int) -> None:
        self._validation_frames = n

    def set_health(self, health: float, tier: str) -> None:
        self._health      = health
        self._health_tier = tier

    def reset_session(self) -> None:
        """Reset per-session counters. Call at route start or after respawn."""
        self._recovery_count    = 0
        self._recovery_history.clear()
        self._fsm_state         = ""
        self._validation_frames = 0


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[NavigationDebugger] = None
_inst_lock = threading.Lock()


def get_navigation_debugger() -> NavigationDebugger:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = NavigationDebugger()
    return _instance
