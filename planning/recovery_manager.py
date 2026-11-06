"""
RecoveryManager — 7-level escalating recovery for navigation failures.

When the navigator detects it cannot confirm position or complete an edge,
RecoveryManager decides WHAT to try next.  Each level is tried in order;
the manager escalates only when the previous level explicitly fails.

Recovery levels (low → high cost):
  1. MICRO_CORRECTION    — release keys, micro-pause, re-scan for anchor
  2. HEADING_REALIGN     — F-reset camera, re-align to expected heading
  3. CHECKPOINT_ROLLBACK — reverse to previous confirmed anchor, re-validate
  4. ALTERNATE_ROUTE     — switch to a different RouteEdge for same destination
  5. ROUTE_RESTART       — return to last_confirmed_anchor and restart route
  6. HIVE_RESET          — navigate to hive_1_entrance (neutral safe point)
  7. FULL_RESET          — press R to respawn; snap localizer to spawn_platform

Each level returns a RecoveryResult indicating:
  - succeeded:  recovery action was successful
  - level:      which level was used
  - new_anchor: where the system believes it is now (if recovered)
  - escalate:   True if the level failed and the caller should try the next one

Public API:
    rm = get_recovery_manager()
    result = rm.attempt(
        level=RecoveryLevel.MICRO_CORRECTION,
        expected_anchor="hive_1_entrance",
        destination="dandelion_field",
        terrain_name="GROUND",
        stop_event=stop_event,
    )
    if not result.succeeded:
        result = rm.attempt(level=RecoveryLevel.HEADING_REALIGN, ...)

    # Or: let RecoveryManager pick the level automatically
    result = rm.escalate(
        from_level=RecoveryLevel.MICRO_CORRECTION,
        expected_anchor=..., destination=..., terrain_name=..., stop_event=...,
    )
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

from navigation.anchor_registry import get_anchor_registry
from navigation.checkpoint_validator import get_checkpoint_validator
from navigation.camera_state import get_camera_state_manager
from world_model.localization_state import get_localization_tracker
from utils.logger import get_logger

log = get_logger(__name__)


# Hard recovery anchors — reaching any of these fully restores localization certainty.
# Priority 1 = try first; each entry: anchor_id → (priority, restore_confidence)
HARD_RECOVERY_ANCHORS: Dict[str, tuple] = {
    "hive_1_entrance": (1, 0.95),
    "spawn_platform":  (2, 0.90),
    "red_cannon_pad":  (3, 0.82),
    "upper_platform":  (4, 0.75),
}


class RecoveryLevel(Enum):
    MICRO_CORRECTION    = 1
    HEADING_REALIGN     = 2
    CHECKPOINT_ROLLBACK = 3
    ALTERNATE_ROUTE     = 4
    ROUTE_RESTART       = 5
    HIVE_RESET          = 6
    FULL_RESET          = 7


# Levels 5 to 7 call Navigator.go_to() from inside a running go_to(), which resets the
# outer recovery state and is refused by the recovery arbiter. Until that is restructured,
# escalation stops here and the route reports failure instead of looping.
_MAX_ESCALATION = RecoveryLevel.ALTERNATE_ROUTE


@dataclass
class RecoveryResult:
    """Outcome of one recovery attempt."""
    succeeded:    bool
    level:        RecoveryLevel
    new_anchor:   Optional[str]   = None
    message:      str             = ""
    escalate:     bool            = False


class RecoveryManager:
    """
    Escalating recovery controller.

    Stateful: tracks escalation history per recovery session.
    A session starts with the first attempt() call and ends when
    reset() is called (typically at route start or confirmed anchor).
    """

    def __init__(self) -> None:
        self._registry  = get_anchor_registry()
        self._validator = get_checkpoint_validator()
        self._csm       = get_camera_state_manager()
        self._tracker   = get_localization_tracker()
        self._session_attempts: int = 0
        self._highest_level: Optional[RecoveryLevel] = None

    # ------------------------------------------------------------------ #
    # Session management                                                  #
    # ------------------------------------------------------------------ #

    def reset(self) -> None:
        """Call at route start or after confirmed anchor to clear escalation state."""
        self._session_attempts = 0
        self._highest_level    = None

    # ------------------------------------------------------------------ #
    # Single-level attempt                                                #
    # ------------------------------------------------------------------ #

    def attempt(
        self,
        level: RecoveryLevel,
        expected_anchor: Optional[str],
        destination: str,
        terrain_name: str,
        stop_event: threading.Event,
    ) -> RecoveryResult:
        """
        Execute one recovery level.

        Returns RecoveryResult.escalate=True if this level failed and the
        caller should try the next level.
        """
        if stop_event.is_set():
            return RecoveryResult(
                succeeded=False,
                level=level,
                message="stop_event set before recovery",
            )

        self._session_attempts += 1
        self._highest_level    = level
        log.info(
            "RecoveryManager[%s]: attempt #%d (expected='%s' dest='%s')",
            level.name, self._session_attempts, expected_anchor, destination,
        )

        handler = {
            RecoveryLevel.MICRO_CORRECTION:    self._micro_correction,
            RecoveryLevel.HEADING_REALIGN:     self._heading_realign,
            RecoveryLevel.CHECKPOINT_ROLLBACK: self._checkpoint_rollback,
            RecoveryLevel.ALTERNATE_ROUTE:     self._alternate_route,
            RecoveryLevel.ROUTE_RESTART:       self._route_restart,
            RecoveryLevel.HIVE_RESET:          self._hive_reset,
            RecoveryLevel.FULL_RESET:          self._full_reset,
        }[level]

        return handler(expected_anchor, destination, terrain_name, stop_event)

    # ------------------------------------------------------------------ #
    # Auto-escalation                                                     #
    # ------------------------------------------------------------------ #

    def escalate(
        self,
        from_level: RecoveryLevel,
        expected_anchor: Optional[str],
        destination: str,
        terrain_name: str,
        stop_event: threading.Event,
    ) -> RecoveryResult:
        """
        Try from_level and escalate through all higher levels until
        one succeeds or FULL_RESET fails.

        Stops if stop_event is set at any point.
        """
        level = from_level
        while True:
            result = self.attempt(level, expected_anchor, destination, terrain_name, stop_event)
            if result.succeeded or stop_event.is_set():
                return result
            if not result.escalate:
                return result
            next_val = level.value + 1
            if next_val > _MAX_ESCALATION.value:
                return RecoveryResult(
                    succeeded=False,
                    level=level,
                    message="All recovery levels exhausted",
                )
            level = RecoveryLevel(next_val)

    # ------------------------------------------------------------------ #
    # Level implementations                                               #
    # ------------------------------------------------------------------ #

    def _micro_correction(
        self,
        expected_anchor: Optional[str],
        destination: str,
        terrain_name: str,
        stop_event: threading.Event,
    ) -> RecoveryResult:
        """
        Release all held keys, wait for physics to settle, re-validate.
        Cost: ~0.5s. Fixes: stuck on geometry, brief detection miss.
        """
        from execution.input_interface import get_input
        inp = get_input()
        inp.release_all()
        time.sleep(0.50)

        if stop_event.is_set():
            return RecoveryResult(succeeded=False, level=RecoveryLevel.MICRO_CORRECTION)

        validation = self._validator.validate(
            expected_anchor=expected_anchor,
            terrain_name=terrain_name,
            heading_deg=self._csm.heading,
            heading_unc=self._csm.heading_uncertainty,
            speed_px_s=0.0,
        )

        if validation.success:
            self._tracker.confirm_anchor(expected_anchor, validation.confidence)
            return RecoveryResult(
                succeeded=True,
                level=RecoveryLevel.MICRO_CORRECTION,
                new_anchor=expected_anchor,
                message=f"micro_correction: re-validated '{expected_anchor}' conf={validation.confidence:.2f}",
            )

        return RecoveryResult(
            succeeded=False,
            level=RecoveryLevel.MICRO_CORRECTION,
            message=f"micro_correction: validation failed conf={validation.confidence:.2f}",
            escalate=True,
        )

    def _heading_realign(
        self,
        expected_anchor: Optional[str],
        destination: str,
        terrain_name: str,
        stop_event: threading.Event,
    ) -> RecoveryResult:
        """
        F-reset camera heading to 0°. Re-validate.
        Cost: ~1.5s. Fixes: camera drifted during traversal, wrong heading.
        """
        ok = self._csm.ensure_traversal_state(stop_event, force=True)
        if not ok or stop_event.is_set():
            return RecoveryResult(
                succeeded=False,
                level=RecoveryLevel.HEADING_REALIGN,
                escalate=True,
            )

        if expected_anchor:
            ok = self._csm.align_for_anchor(expected_anchor, stop_event)
            if not ok or stop_event.is_set():
                return RecoveryResult(
                    succeeded=False,
                    level=RecoveryLevel.HEADING_REALIGN,
                    escalate=True,
                )

        validation = self._validator.validate(
            expected_anchor=expected_anchor,
            terrain_name=terrain_name,
            heading_deg=self._csm.heading,
            heading_unc=self._csm.heading_uncertainty,
            speed_px_s=0.0,
        )

        if validation.success:
            self._tracker.confirm_anchor(expected_anchor, validation.confidence)
            return RecoveryResult(
                succeeded=True,
                level=RecoveryLevel.HEADING_REALIGN,
                new_anchor=expected_anchor,
                message=f"heading_realign: validated '{expected_anchor}'",
            )

        return RecoveryResult(
            succeeded=False,
            level=RecoveryLevel.HEADING_REALIGN,
            message="heading_realign: still not confirmed after realign",
            escalate=True,
        )

    def _checkpoint_rollback(
        self,
        expected_anchor: Optional[str],
        destination: str,
        terrain_name: str,
        stop_event: threading.Event,
    ) -> RecoveryResult:
        """
        Try to scan for ANY anchor to establish position, then replan.
        Cost: ~2-3s. Fixes: drifted partway along an edge.
        """
        scan_result = self._validator.scan_for_any(
            terrain_name=terrain_name,
            heading_deg=self._csm.heading,
            heading_unc=self._csm.heading_uncertainty,
            speed_px_s=0.0,
        )

        if scan_result and scan_result.matched_anchor:
            anchor_id = scan_result.matched_anchor
            self._tracker.confirm_anchor(anchor_id, scan_result.confidence)
            log.info("checkpoint_rollback: found anchor '%s' conf=%.2f", anchor_id, scan_result.confidence)
            return RecoveryResult(
                succeeded=True,
                level=RecoveryLevel.CHECKPOINT_ROLLBACK,
                new_anchor=anchor_id,
                message=f"checkpoint_rollback: located at '{anchor_id}'",
            )

        # Try scanning neighbors of expected anchor
        if expected_anchor:
            neighbors = self._registry.neighbors_of(expected_anchor)
            for nb in neighbors:
                validation = self._validator.validate(
                    expected_anchor=nb.id,
                    terrain_name=terrain_name,
                    heading_deg=self._csm.heading,
                    heading_unc=self._csm.heading_uncertainty,
                    speed_px_s=0.0,
                )
                if validation.success:
                    self._tracker.confirm_anchor(nb.id, validation.confidence)
                    return RecoveryResult(
                        succeeded=True,
                        level=RecoveryLevel.CHECKPOINT_ROLLBACK,
                        new_anchor=nb.id,
                        message=f"checkpoint_rollback: found neighbor '{nb.id}'",
                    )

        return RecoveryResult(
            succeeded=False,
            level=RecoveryLevel.CHECKPOINT_ROLLBACK,
            message="checkpoint_rollback: no anchor found in scan",
            escalate=True,
        )

    def _alternate_route(
        self,
        expected_anchor: Optional[str],
        destination: str,
        terrain_name: str,
        stop_event: threading.Event,
    ) -> RecoveryResult:
        """
        Signal to the navigator to replan via a different path.
        This level doesn't move — it just returns succeeded=True with a
        message instructing the caller to replan (avoids re-entering the
        failed edge).
        Cost: 0s (planning only). Fixes: specific edge consistently failing.
        """
        state = self._tracker.state
        current = state.probable_anchor or state.last_confirmed_anchor

        if current is None:
            return RecoveryResult(
                succeeded=False,
                level=RecoveryLevel.ALTERNATE_ROUTE,
                message="alternate_route: current position unknown",
                escalate=True,
            )

        # Simply returning succeeded=True with current position allows
        # the navigator to replan from current → destination, naturally
        # avoiding the failed edge if an alternate path exists.
        return RecoveryResult(
            succeeded=True,
            level=RecoveryLevel.ALTERNATE_ROUTE,
            new_anchor=current,
            message=f"alternate_route: replan from '{current}' to '{destination}'",
        )

    def _route_restart(
        self,
        expected_anchor: Optional[str],
        destination: str,
        terrain_name: str,
        stop_event: threading.Event,
    ) -> RecoveryResult:
        """
        Navigate to the nearest hard recovery anchor (deterministic certainty restore).
        Cost: depends on distance. Fixes: badly off-course.
        """
        state      = self._tracker.state
        last_known = state.last_confirmed_anchor

        # Prefer hard recovery anchors over last_known
        target = self._nearest_hard_anchor(last_known, expected_anchor)

        if not target:
            return RecoveryResult(
                succeeded=False,
                level=RecoveryLevel.ROUTE_RESTART,
                message="route_restart: no viable target anchor",
                escalate=True,
            )

        log.info("route_restart: navigating to hard anchor '%s'", target)
        from navigation.navigator import get_navigator
        nav = get_navigator()
        ok = nav.go_to(target, stop_event, normalize_camera=True)

        if ok:
            restore_conf = HARD_RECOVERY_ANCHORS.get(target, (99, 0.80))[1]
            self._tracker.confirm_anchor(target, restore_conf)
            return RecoveryResult(
                succeeded=True,
                level=RecoveryLevel.ROUTE_RESTART,
                new_anchor=target,
                message=f"route_restart: reached hard anchor '{target}' conf={restore_conf}",
            )

        return RecoveryResult(
            succeeded=False,
            level=RecoveryLevel.ROUTE_RESTART,
            message=f"route_restart: could not reach '{target}'",
            escalate=True,
        )

    def _nearest_hard_anchor(
        self,
        last_known: Optional[str],
        expected_anchor: Optional[str],
    ) -> Optional[str]:
        """
        Pick the best hard anchor to navigate to during recovery.

        Priority:
          1. last_known if it IS a hard anchor
          2. Lowest-priority-number hard anchor that isn't expected_anchor
        """
        # If last_known is already a hard anchor, return to it
        if last_known and last_known in HARD_RECOVERY_ANCHORS:
            if last_known != expected_anchor:
                return last_known

        # Otherwise pick lowest-priority hard anchor (skip expected if stuck there)
        candidates = sorted(HARD_RECOVERY_ANCHORS.items(), key=lambda x: x[1][0])
        for anchor_id, _ in candidates:
            if anchor_id != expected_anchor:
                return anchor_id

        # Fallback: any hard anchor
        return next(iter(HARD_RECOVERY_ANCHORS), None)

    def _hive_reset(
        self,
        expected_anchor: Optional[str],
        destination: str,
        terrain_name: str,
        stop_event: threading.Event,
    ) -> RecoveryResult:
        """
        Navigate to hive_1_entrance — the universally safe neutral point.
        Cost: depends on distance. Fixes: lost far from origin.
        """
        log.info("hive_reset: navigating to hive_1_entrance")
        from navigation.navigator import get_navigator
        nav = get_navigator()
        ok = nav.go_to("hive_1_entrance", stop_event, normalize_camera=True)

        if ok:
            self._tracker.confirm_anchor("hive_1_entrance", 0.90)
            return RecoveryResult(
                succeeded=True,
                level=RecoveryLevel.HIVE_RESET,
                new_anchor="hive_1_entrance",
                message="hive_reset: at hive_1_entrance",
            )

        return RecoveryResult(
            succeeded=False,
            level=RecoveryLevel.HIVE_RESET,
            message="hive_reset: could not navigate to hive",
            escalate=True,
        )

    def _full_reset(
        self,
        expected_anchor: Optional[str],
        destination: str,
        terrain_name: str,
        stop_event: threading.Event,
    ) -> RecoveryResult:
        """
        Press R to respawn. Snap localizer to spawn_platform.
        Cost: ~8-10s. Fixes: physically impossible position, death loop.
        """
        log.warning("full_reset: pressing R — this resets the character")
        from navigation.primitives.actions import ResetCharacter
        from navigation.navigator import get_navigator

        primitive = ResetCharacter(reset_wait_sec=8.0)
        result    = primitive.execute(stop_event)

        if result.success:
            nav = get_navigator()
            nav.snap_spawn()
            self._tracker.snap_to("spawn_platform", 0.95)
            return RecoveryResult(
                succeeded=True,
                level=RecoveryLevel.FULL_RESET,
                new_anchor="spawn_platform",
                message="full_reset: respawned at spawn_platform",
            )

        return RecoveryResult(
            succeeded=False,
            level=RecoveryLevel.FULL_RESET,
            message="full_reset: respawn not detected",
            escalate=False,  # no higher level exists
        )


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[RecoveryManager] = None
_inst_lock = threading.Lock()


def get_recovery_manager() -> RecoveryManager:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = RecoveryManager()
    return _instance
