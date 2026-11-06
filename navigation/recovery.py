"""
Recovery — stuck and position-loss behaviors for the navigation stack.

Two recovery modes:
  1. Unstick — player is physically stuck (wall, ledge, obstacle).
     Uses escalating strategies: jump → strafe+jump → back+jump → reset.

  2. Reorient — player position is unknown (localizer lost confidence).
     Scans the current frame for any registered landmark, snaps localizer
     if a strong sighting is found, returns whether reorientation succeeded.

Both modes track retry counts per navigation attempt.
Call reset_retries() when a new segment starts successfully.
Raise RecoveryFailed after MAX_RETRIES exhausted.

Public API:
    rec = Recovery(localizer, landmark_detector, screen_capture)
    rec.unstick(stop_event)           # stuck in terrain
    ok  = rec.reorient(stop_event)    # lost position
    rec.reset_retries()
"""
from __future__ import annotations

import random
import threading
import time
from typing import Optional

from navigation.types import LandmarkReading
from utils.logger import get_logger

log = get_logger(__name__)

_MAX_UNSTICK   = 5
_MAX_REORIENT  = 3
_OPPOSITE      = {"w": "s", "s": "w", "a": "d", "d": "a"}


class RecoveryFailed(RuntimeError):
    pass


class Recovery:
    """
    Per-navigation-session recovery manager.

    Instantiated by Navigator and passed to MovementExecutor so walk bursts
    can trigger unstick on stall.
    """

    def __init__(self, localizer, landmark_detector, screen_capture) -> None:
        self._loc  = localizer
        self._det  = landmark_detector
        self._sc   = screen_capture
        self._nav_map = None   # set lazily

        self._unstick_count  = 0
        self._reorient_count = 0
        self._last_key: str  = "w"

    def set_last_key(self, key: str) -> None:
        """Call before each walk burst so unstick knows the held direction."""
        self._last_key = key

    def reset_retries(self) -> None:
        self._unstick_count  = 0
        self._reorient_count = 0

    # ------------------------------------------------------------------ #
    # Unstick                                                              #
    # ------------------------------------------------------------------ #

    def unstick(self, stop_event: threading.Event, held_key: Optional[str] = None) -> None:
        """
        Execute one unstick step.

        Raises RecoveryFailed after MAX_UNSTICK consecutive calls.
        """
        key = held_key or self._last_key
        self._unstick_count += 1

        if self._unstick_count > _MAX_UNSTICK:
            raise RecoveryFailed(
                f"Stuck after {_MAX_UNSTICK} unstick attempts"
            )

        log.warning("Unstick attempt %d/%d (held=%s)", self._unstick_count, _MAX_UNSTICK, key)

        try:
            from execution.input_interface import get_input
            inp = get_input()

            if self._unstick_count == 1:
                # Jump to clear small obstacles
                inp.tap_key("space")
                time.sleep(0.35)

            elif self._unstick_count == 2:
                # Random strafe then jump
                strafe = random.choice(["a", "d"])
                inp.press_key(strafe, 0.45, jitter=False)
                inp.tap_key("space")
                time.sleep(0.25)

            elif self._unstick_count == 3:
                # Back up + jump
                opp = _OPPOSITE.get(key, "s")
                inp.press_key(opp, 0.60, jitter=False)
                inp.tap_key("space")
                time.sleep(0.30)

            elif self._unstick_count == 4:
                # Full release → wait → strafe forward
                inp.release_all()
                time.sleep(0.80)
                strafe = random.choice(["a", "d"])
                inp.press_key(strafe, 0.55, jitter=False)
                time.sleep(0.20)

            else:
                # Last resort: back away diagonally and jump
                inp.release_all()
                opp = _OPPOSITE.get(key, "s")
                strafe = random.choice(["a", "d"])
                inp.press_key(opp, 0.40, jitter=False)
                inp.press_key(strafe, 0.40, jitter=False)
                inp.tap_key("space")
                time.sleep(0.50)

        except Exception as exc:
            log.debug("Unstick action error: %s", exc)

    # ------------------------------------------------------------------ #
    # Reorient (position loss)                                             #
    # ------------------------------------------------------------------ #

    def reorient(
        self,
        stop_event: threading.Event,
        known_landmarks: Optional[list] = None,
    ) -> bool:
        """
        Attempt to recover position estimate by scanning for any landmark.

        Returns True if a landmark was found and localizer was snapped.
        Returns False if no landmark found (position still unknown).
        """
        self._reorient_count += 1
        if self._reorient_count > _MAX_REORIENT:
            raise RecoveryFailed(
                f"Position lost after {_MAX_REORIENT} reorient attempts"
            )

        log.warning("Reorient attempt %d/%d", self._reorient_count, _MAX_REORIENT)

        if stop_event.is_set():
            return False

        # Slow rotation to scan surroundings
        self._scan_rotation(stop_event)

        if stop_event.is_set():
            return False

        frame = self._sc.capture_full()
        if frame is None:
            return False

        scan_names = known_landmarks or self._det.available_landmarks()
        readings   = self._det.scan(frame, names=scan_names)

        if not readings:
            log.debug("Reorient: no landmarks detected")
            return False

        best = readings[0]
        if best.confidence < 0.50:
            log.debug("Reorient: best landmark '%s' conf=%.2f below threshold",
                      best.name, best.confidence)
            return False

        # Snap localizer to the node that owns this landmark
        self._loc.observe(best)
        node = self._loc.current_node
        if node:
            log.info("Reorient: snapped to '%s' via landmark '%s' (conf=%.2f)",
                     node, best.name, best.confidence)
            return True

        log.debug("Reorient: landmark '%s' found but no unique node", best.name)
        return False

    def _scan_rotation(self, stop_event: threading.Event) -> None:
        """
        Slowly rotate view to sample surroundings.
        Uses a sequence of brief right-strafe + look pauses.
        """
        if stop_event.is_set():
            return
        try:
            from execution.input_interface import get_input
            inp = get_input()
            # Slight left-right oscillation to expose more visual context
            for _ in range(2):
                if stop_event.is_set():
                    break
                inp.press_key("a", 0.30, jitter=False)
                time.sleep(0.12)
                inp.press_key("d", 0.30, jitter=False)
                time.sleep(0.12)
        except Exception as exc:
            log.debug("Scan rotation error: %s", exc)
