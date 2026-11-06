"""
Red Cannon traversal controller.

Execution flow:
  1. Optional alignment walk (cannon_align_keys)
  2. Activate cannon (press cannon_key, default 'e') — retry up to 3×
  3. Detect launch via optical-flow speed spike (> FLIGHT_THRESHOLD × base)
  4. Monitor flight until landing (LAND_WINDOW consecutive low-speed samples)
  5. Post-landing brake burst to absorb residual momentum
  6. Reset optical-flow history

Landing detection uses hysteresis: we must first observe flight-speed
(confirms launch happened), then watch for it to drop.  This prevents
false positives from pre-launch camera wobble.

If no speed spike is seen within LAUNCH_TIMEOUT seconds after activation,
the attempt is retried up to MAX_ATTEMPTS times before declaring failure.
"""
from __future__ import annotations

import threading
import time
from typing import List, Optional, Tuple

from detection.screen_capture import get_screen_capture
from movement.position_detector import PositionDetector
from movement.randomizer import human_sleep
from utils.logger import get_logger

log = get_logger(__name__)

# Speed thresholds (multiples of calibrated base speed)
FLIGHT_THRESHOLD = 2.0    # speed ratio above which player is considered airborne
LAND_THRESHOLD   = 0.25   # speed ratio below which player is considered landed

# Window / timing
LAND_WINDOW      = 4      # consecutive below-threshold samples → landed
ACTIVATION_WAIT  = 0.8    # seconds after keypress before measuring for launch
LAUNCH_TIMEOUT   = 4.5    # max seconds to detect speed spike
FLIGHT_TIMEOUT   = 14.0   # safety cut-off if landing never detected
SAMPLE_INTERVAL  = 0.055  # seconds between optical-flow samples
MAX_ATTEMPTS     = 3


class CannonController:
    """
    Executes a single Red Cannon launch sequence.

    Instantiated by Nav3D; safe to reuse across multiple cannon segments
    within one navigation session (state is reset per execute() call).
    """

    def __init__(self) -> None:
        self._sc       = get_screen_capture()
        self._detector = PositionDetector()

    def execute(
        self,
        cannon_key: str,
        align_keys: List[Tuple[str, float]],
        expected_air_time: float,
        base_speed: float,
        stop_event: threading.Event,
    ) -> bool:
        """
        Run a full cannon traversal sequence.

        Returns True on confirmed landing (or assumed landing after timeout),
        False if the cannon could not be activated or stop_event was set.
        """
        if stop_event.is_set():
            return False

        # 1. Alignment walk
        for key, dur in align_keys:
            if stop_event.is_set():
                return False
            try:
                import pyautogui
                pyautogui.keyDown(key)
                time.sleep(dur)
                pyautogui.keyUp(key)
            except Exception as exc:
                log.debug("Cannon align key error: %s", exc)
            time.sleep(0.04)

        human_sleep(150, 30)

        # 2. Activation with retry
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if stop_event.is_set():
                return False
            log.info("Cannon activation attempt %d/%d", attempt, MAX_ATTEMPTS)
            try:
                import pyautogui
                pyautogui.press(cannon_key)
            except Exception as exc:
                log.debug("Cannon key error: %s", exc)
                return False
            time.sleep(ACTIVATION_WAIT)

            launched = self._wait_for_launch(base_speed, stop_event)
            if launched:
                log.info("Cannon: launch confirmed on attempt %d", attempt)
                break
            log.warning("Cannon: no launch spike detected on attempt %d", attempt)
            human_sleep(900, 100)
        else:
            log.error("Cannon: failed to launch after %d attempts", MAX_ATTEMPTS)
            return False

        # 3. Monitor flight → landing
        landed = self._wait_for_landing(base_speed, expected_air_time, stop_event)
        if not landed:
            log.warning("Cannon: landing not confirmed — assuming arrived")

        # 4. Post-landing brake
        self._brake(stop_event)
        self._detector.reset()
        return True

    # ------------------------------------------------------------------ #

    def _wait_for_launch(self, base_speed: float, stop_event: threading.Event) -> bool:
        """Return True when optical-flow speed exceeds flight threshold."""
        threshold = base_speed * FLIGHT_THRESHOLD if base_speed > 1.0 else 50.0
        t0 = time.monotonic()
        while time.monotonic() - t0 < LAUNCH_TIMEOUT:
            if stop_event.is_set():
                return False
            frame = self._sc.capture_full()
            if frame is not None:
                d = self._detector.push_frame(frame)
                if d and d.speed > threshold and d.confidence > 0.2:
                    return True
            time.sleep(SAMPLE_INTERVAL)
        return False

    def _wait_for_landing(
        self,
        base_speed: float,
        expected_air_time: float,
        stop_event: threading.Event,
    ) -> bool:
        """
        Wait until speed stays below LAND_THRESHOLD for LAND_WINDOW consecutive
        samples.  Must first observe one above-threshold sample to arm the detector.
        """
        land_thresh  = base_speed * LAND_THRESHOLD if base_speed > 1.0 else 8.0
        below_count  = 0
        armed        = False          # True once we've seen high-speed flight
        t0           = time.monotonic()
        max_time     = max(FLIGHT_TIMEOUT, expected_air_time * 2.2)

        while time.monotonic() - t0 < max_time:
            if stop_event.is_set():
                return False
            frame = self._sc.capture_full()
            if frame is not None:
                d = self._detector.push_frame(frame)
                if d and d.confidence > 0.15:
                    if d.speed > land_thresh * 2:
                        armed = True
                        below_count = 0
                    elif armed and d.speed < land_thresh:
                        below_count += 1
                        if below_count >= LAND_WINDOW:
                            elapsed = time.monotonic() - t0
                            log.info("Cannon: landing confirmed (%.2fs air)", elapsed)
                            return True
                    else:
                        below_count = 0
            time.sleep(SAMPLE_INTERVAL)
        return False

    def _brake(self, stop_event: threading.Event) -> None:
        """Brief S-key brake to absorb landing momentum."""
        if stop_event.is_set():
            return
        try:
            import pyautogui
            pyautogui.keyDown("s")
            time.sleep(0.22)
            pyautogui.keyUp("s")
            human_sleep(100, 20)
        except Exception as exc:
            log.debug("Cannon brake error: %s", exc)
