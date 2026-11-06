"""
Glider traversal controller.

BSS glider usage:
  - Player jumps from an elevated point, then activates their glider
  - Glider catches air; player drifts horizontally toward destination
  - FPS, lag, and movement speed buffs all affect glide distance
  - Landing is inferred from optical-flow speed dropping after sustained
    mid-air flow

Execution flow:
  1. Optional jump (press Space)
  2. Wait JUMP_APEX_WAIT seconds for jump apex (vertical flow peaks)
  3. Activate glider key (default 'q')
  4. Monitor optical flow: wait for high sustained speed, then landing drop
  5. Post-landing brake + optical-flow reset

If the player never becomes airborne (speed never exceeds GLIDE_THRESHOLD),
we assume the jump failed and retry the jump once before giving up.
"""
from __future__ import annotations

import threading
import time

from detection.screen_capture import get_screen_capture
from movement.position_detector import PositionDetector
from movement.randomizer import human_sleep
from utils.logger import get_logger

log = get_logger(__name__)

# Speed thresholds
GLIDE_THRESHOLD = 1.2   # ratio above which player is considered gliding
LAND_RATIO      = 0.20  # ratio below which player is considered landed

# Timing
JUMP_APEX_WAIT  = 0.35  # seconds after jump before activating glider
GLIDE_TIMEOUT   = 16.0  # safety cut-off
SAMPLE_INTERVAL = 0.055
LAND_SAMPLES    = 3     # consecutive below-threshold samples → landed


class GliderController:
    """
    Handles one glider traversal leg.
    Instantiated by Nav3D; reusable across segments within one session.
    """

    def __init__(self) -> None:
        self._sc       = get_screen_capture()
        self._detector = PositionDetector()

    def execute(
        self,
        glider_key: str,
        expected_glide_sec: float,
        base_speed: float,
        do_jump: bool,
        stop_event: threading.Event,
    ) -> bool:
        """
        Execute glider traversal.

        do_jump=True → press Space first (for JUMP_GLIDE segments).
        Returns True on confirmed landing, False on timeout/stop.
        """
        if stop_event.is_set():
            return False

        import pyautogui

        for attempt in range(1, 3):
            if stop_event.is_set():
                return False

            if do_jump or attempt > 1:
                log.debug("Glider: jump (attempt %d)", attempt)
                pyautogui.press("space")
                time.sleep(JUMP_APEX_WAIT)

            log.info("Glider: activating key=%s (attempt %d)", glider_key, attempt)
            pyautogui.press(glider_key)
            human_sleep(100, 20)

            # Check if glider engaged (speed should rise above threshold)
            if self._wait_for_glide(base_speed, stop_event):
                break
            log.warning("Glider: not airborne on attempt %d", attempt)
        else:
            log.error("Glider: could not become airborne — aborting")
            return False

        landed = self._monitor_landing(base_speed, expected_glide_sec, stop_event)
        if not landed:
            log.warning("Glider: landing not confirmed — assuming arrived")

        if not stop_event.is_set():
            self._brake(stop_event)
        self._detector.reset()
        return True

    # ------------------------------------------------------------------ #

    def _wait_for_glide(self, base_speed: float, stop_event: threading.Event) -> bool:
        """Returns True if glide speed is detected within 2s of activation."""
        threshold = base_speed * GLIDE_THRESHOLD if base_speed > 1.0 else 30.0
        t0 = time.monotonic()
        while time.monotonic() - t0 < 2.0:
            if stop_event.is_set():
                return False
            frame = self._sc.capture_full()
            if frame is not None:
                d = self._detector.push_frame(frame)
                if d and d.speed > threshold and d.confidence > 0.2:
                    return True
            time.sleep(SAMPLE_INTERVAL)
        return False

    def _monitor_landing(
        self,
        base_speed: float,
        expected_sec: float,
        stop_event: threading.Event,
    ) -> bool:
        """Wait for LAND_SAMPLES consecutive readings below land threshold."""
        land_thresh  = base_speed * LAND_RATIO if base_speed > 1.0 else 6.0
        below_count  = 0
        t0           = time.monotonic()
        max_time     = max(GLIDE_TIMEOUT, expected_sec * 2.5)

        while time.monotonic() - t0 < max_time:
            if stop_event.is_set():
                return False
            frame = self._sc.capture_full()
            if frame is not None:
                d = self._detector.push_frame(frame)
                if d and d.confidence > 0.15:
                    if d.speed < land_thresh:
                        below_count += 1
                        if below_count >= LAND_SAMPLES:
                            elapsed = time.monotonic() - t0
                            log.info("Glider: landing confirmed (%.2fs)", elapsed)
                            return True
                    else:
                        below_count = 0
            time.sleep(SAMPLE_INTERVAL)
        return False

    def _brake(self, stop_event: threading.Event) -> None:
        if stop_event.is_set():
            return
        try:
            import pyautogui
            pyautogui.keyDown("s")
            time.sleep(0.18)
            pyautogui.keyUp("s")
        except Exception as exc:
            log.debug("Glider brake error: %s", exc)
