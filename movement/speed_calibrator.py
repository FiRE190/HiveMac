"""
Baseline movement speed calibration.

Moves the player forward (W key) for MEASURE_SEC seconds while sampling
optical-flow magnitude.  The mean result is stored as base_speed_px_s and
used by AdaptiveController to normalise burst durations against the current
speed state (buffed / normal / slowed).

Typical values:
  - Unbuffed:         ~80–150 px/s
  - Haste buff:       ~200–350 px/s
  - Speed token:      ~250–400 px/s
  - Slowed/lag:       ~30–60  px/s
"""
from __future__ import annotations

import time
import threading
from typing import Optional

from utils.logger import get_logger

log = get_logger(__name__)

MEASURE_SEC     = 2.0   # seconds to hold W during calibration
SAMPLE_INTERVAL = 0.05  # one frame every 50 ms → ~40 samples total

_CONFIG_KEY = "movement.base_speed_px_s"


class SpeedCalibrator:
    """
    Measures and stores the player's baseline movement speed.

    Thread-safe for reads; calibrate() should only be called from one
    thread at a time (it physically presses W and blocks for MEASURE_SEC).
    """

    def __init__(self) -> None:
        self._base_speed: Optional[float] = None
        self._lock = threading.Lock()
        self._load_from_config()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def calibrate(self, stop_event: threading.Event) -> float:
        """
        Hold the W key for MEASURE_SEC seconds while sampling optical flow.

        Persists the measured base_speed to config and returns it (px/s).
        Returns 0.0 if the measurement fails (cv2 unavailable, etc.).
        """
        try:
            import pyautogui
            from detection.screen_capture import get_screen_capture
            from movement.position_detector import PositionDetector
        except ImportError as exc:
            log.warning("Speed calibration unavailable: %s", exc)
            return 0.0

        sc       = get_screen_capture()
        detector = PositionDetector()
        samples: list[float] = []

        try:
            from calibration.roblox_finder import focus_roblox
            focus_roblox()
            time.sleep(0.4)  # give OS time to bring Roblox to front
        except Exception:
            pass

        log.info("Speed calibration: pressing W for %.1fs", MEASURE_SEC)
        pyautogui.keyDown("w")
        t0 = time.monotonic()

        try:
            while time.monotonic() - t0 < MEASURE_SEC:
                if stop_event.is_set():
                    break
                frame = sc.capture_full()
                if frame is not None:
                    delta = detector.push_frame(frame)
                    if delta and delta.confidence > 0.3:
                        samples.append(delta.speed)
                time.sleep(SAMPLE_INTERVAL)
        finally:
            pyautogui.keyUp("w")

        if not samples:
            log.warning("Speed calibration: no valid optical-flow samples collected")
            return 0.0

        base = float(sum(samples) / len(samples))
        with self._lock:
            self._base_speed = base
        self._save_to_config(base)
        log.info("Base speed calibrated: %.1f px/s  (%d samples)", base, len(samples))
        return base

    def get_base_speed(self) -> float:
        """Return cached base speed in px/s, or 0 if uncalibrated."""
        with self._lock:
            return self._base_speed or 0.0

    def speed_ratio(self, current_px_s: float) -> float:
        """
        current / base_speed.

        Returns 1.0 when uncalibrated so burst durations stay at default.
        Returns 0.0 when current_px_s is 0 (player not moving / can't measure).
        """
        with self._lock:
            base = self._base_speed
        if not base or base == 0.0:
            return 1.0
        return current_px_s / base

    def classify(self, current_px_s: float) -> str:
        """Return "boosted", "normal", or "slowed" relative to base speed."""
        ratio = self.speed_ratio(current_px_s)
        if ratio > 1.25:
            return "boosted"
        if ratio < 0.70:
            return "slowed"
        return "normal"

    # ------------------------------------------------------------------ #

    def _load_from_config(self) -> None:
        try:
            from config.config_manager import get_config
            val = get_config().get(_CONFIG_KEY, 0)
            if val:
                self._base_speed = float(val)
                log.debug("Loaded cached base_speed=%.1f px/s", self._base_speed)
        except Exception:
            pass

    def _save_to_config(self, speed: float) -> None:
        try:
            from config.config_manager import get_config
            get_config().set(_CONFIG_KEY, speed)
        except Exception:
            pass
