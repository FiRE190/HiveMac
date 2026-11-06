"""
RecoveryArbiter — serialized recovery lock with precedence enforcement.

PROBLEM SOLVED:
  Without arbitration, three independent systems can each trigger recovery
  simultaneously:
    1. NavigationHealth (proactive / health preempt)
    2. RouteFSM (edge-level validation failure)
    3. Navigator (post-edge manual check)

  If all three fire in the same execution window, LocalizationEngine receives
  multiple `confirm_anchor()` calls from different recovery anchors in rapid
  succession, producing contradictory belief updates and recovery loops.

SOLUTION — single serialized lock with precedence:

  Recovery precedence (higher wins):
    HARD  (priority 10): ROUTE_RESTART, HIVE_RESET, FULL_RESET
    EDGE  (priority  5): FSM edge-level recovery (MICRO through ALTERNATE)
    SOFT  (priority  1): health preempt (HEADING_REALIGN or less)

  Rules:
    1. Only ONE recovery may be active at any time
    2. A higher-priority request may preempt a lower-priority active recovery
    3. HEALTH_PREEMPT is denied if EDGE or HARD recovery is already active
    4. Releasing a lock that wasn't acquired is a no-op (safe)
    5. Max 2 recovery attempts per edge (per-edge count tracked separately)

  Navigator / FSM usage:
    with recovery_arbiter.lock("FSM_RECOVERY", RecoveryLevel.MICRO_CORRECTION):
        ... run recovery ...
    # lock is released automatically even on exception

Public API:
    arb = get_recovery_arbiter()
    if arb.acquire("HEALTH_PREEMPT", RecoveryLevel.HEADING_REALIGN):
        try:
            run_recovery(...)
        finally:
            arb.release("HEALTH_PREEMPT")
    else:
        log.debug("Recovery skipped: %s already active", arb.active_source)
"""
from __future__ import annotations

import contextlib
import threading
import time
from dataclasses import dataclass
from typing import Optional

from planning.recovery_manager import RecoveryLevel
from utils.logger import get_logger

log = get_logger(__name__)

# Source names and their priority (higher = more important)
_PRIORITY = {
    "HARD_RESET":     10,
    "FSM_RECOVERY":    5,
    "HEALTH_PREEMPT":  1,
}

# Per-edge max recovery attempts (prevents thrashing on a single edge)
_MAX_RECOVERY_PER_EDGE = 2

# If a recovery lock is held longer than this, it is considered stale and
# auto-expired on the next is_active check. Protects against a hung
# RecoveryManager starving HEALTH_PREEMPT indefinitely.
_MAX_LOCK_HOLD_SEC = 30.0

# RecoveryLevel → source bucket
def _source_for_level(level: RecoveryLevel) -> str:
    if level.value >= RecoveryLevel.ROUTE_RESTART.value:
        return "HARD_RESET"
    return "FSM_RECOVERY"


@dataclass
class _Lock:
    source:      str
    priority:    int
    level:       RecoveryLevel
    acquired_at: float


class RecoveryArbiter:
    """
    Session-level recovery serialization lock.

    Thread-safe. Call acquire() before starting any recovery action.
    Call release() (or use the context manager) after completion.
    """

    def __init__(self) -> None:
        self._mutex   = threading.Lock()
        self._active: Optional[_Lock] = None
        # Per-edge recovery counts: edge_key → count
        self._edge_counts: dict = {}

    # ------------------------------------------------------------------ #
    # Acquire / release                                                   #
    # ------------------------------------------------------------------ #

    def acquire(self, source: str, level: RecoveryLevel) -> bool:
        """
        Try to acquire the recovery lock for source/level.

        Returns True if granted, False if denied (another recovery is
        active with equal or higher priority).
        """
        priority = _PRIORITY.get(source, 1)
        with self._mutex:
            if self._active is None:
                self._active = _Lock(
                    source=source, priority=priority,
                    level=level, acquired_at=time.monotonic(),
                )
                log.debug("RecoveryArbiter: %s acquired [%s]", source, level.name)
                return True

            if priority > self._active.priority:
                log.info(
                    "RecoveryArbiter: %s preempts %s (pri %d > %d)",
                    source, self._active.source, priority, self._active.priority,
                )
                self._active = _Lock(
                    source=source, priority=priority,
                    level=level, acquired_at=time.monotonic(),
                )
                return True

            log.debug(
                "RecoveryArbiter: %s denied — %s already active (pri %d >= %d)",
                source, self._active.source, self._active.priority, priority,
            )
            return False

    def release(self, source: str) -> None:
        """Release the lock if held by source. No-op if not held by source."""
        with self._mutex:
            if self._active and self._active.source == source:
                log.debug(
                    "RecoveryArbiter: %s released (held %.2fs)",
                    source, time.monotonic() - self._active.acquired_at,
                )
                self._active = None

    # ------------------------------------------------------------------ #
    # Per-edge throttling                                                 #
    # ------------------------------------------------------------------ #

    def peek_edge_budget(self, edge_key: str) -> bool:
        """
        Returns True if this edge has remaining recovery budget.
        Does NOT consume the budget — use before acquiring the lock
        to avoid consuming a budget slot on a denied acquire.
        """
        with self._mutex:
            return self._edge_counts.get(edge_key, 0) < _MAX_RECOVERY_PER_EDGE

    def check_edge_budget(self, edge_key: str) -> bool:
        """
        Returns True if this edge has remaining recovery budget and
        consumes one slot. Call only after successfully acquiring the lock.
        """
        with self._mutex:
            count = self._edge_counts.get(edge_key, 0)
            if count >= _MAX_RECOVERY_PER_EDGE:
                log.debug(
                    "RecoveryArbiter: edge '%s' budget exhausted (%d/%d)",
                    edge_key, count, _MAX_RECOVERY_PER_EDGE,
                )
                return False
            self._edge_counts[edge_key] = count + 1
            return True

    def reset_edge(self, edge_key: str) -> None:
        with self._mutex:
            self._edge_counts.pop(edge_key, None)

    def reset_all_edges(self) -> None:
        with self._mutex:
            self._edge_counts.clear()

    # ------------------------------------------------------------------ #
    # Context manager                                                     #
    # ------------------------------------------------------------------ #

    @contextlib.contextmanager
    def lock(self, source: str, level: RecoveryLevel):
        """
        Context manager form: auto-releases on exit or exception.

        Usage:
            with arbiter.lock("FSM_RECOVERY", RecoveryLevel.MICRO_CORRECTION) as granted:
                if not granted:
                    return   # skip recovery
                run_recovery(...)
        """
        granted = self.acquire(source, level)
        try:
            yield granted
        finally:
            if granted:
                self.release(source)

    # ------------------------------------------------------------------ #
    # State queries                                                       #
    # ------------------------------------------------------------------ #

    @property
    def is_active(self) -> bool:
        with self._mutex:
            if self._active is None:
                return False
            held = time.monotonic() - self._active.acquired_at
            if held > _MAX_LOCK_HOLD_SEC:
                # Stale lock — recovery hung or caller forgot to release.
                # Auto-expire so the runtime can continue rather than
                # permanently blocking all future recovery attempts.
                log.warning(
                    "RecoveryArbiter: auto-expiring stale %s lock (held %.1fs > %.0fs limit)",
                    self._active.source, held, _MAX_LOCK_HOLD_SEC,
                )
                self._active = None
                return False
            return True

    @property
    def active_source(self) -> Optional[str]:
        with self._mutex:
            return self._active.source if self._active else None

    @property
    def active_level(self) -> Optional[RecoveryLevel]:
        with self._mutex:
            return self._active.level if self._active else None

    def reset(self) -> None:
        """Full reset — call at route start or after respawn."""
        with self._mutex:
            self._active = None
            self._edge_counts.clear()


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[RecoveryArbiter] = None
_inst_lock = threading.Lock()


def get_recovery_arbiter() -> RecoveryArbiter:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = RecoveryArbiter()
    return _instance
