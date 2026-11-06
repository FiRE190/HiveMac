"""
Camera alignment — normalize camera to a consistent heading before navigation.

In BSS the third-person camera follows the player but can be rotated freely.
WASD movement is camera-relative, so inconsistent camera angles produce
inconsistent navigation results.

The camera heading model:
  - After normalize() (F key reset): heading = 0°, uncertainty = low
  - After rotate(n): heading shifts by n × _DEGREES_PER_TAP
  - During movement: optical flow direction refines heading estimate
  - Heading uncertainty grows over time without a reset or landmark fix

Heading convention: 0° = default forward after F reset (roughly toward spawn).
Positive = rotated clockwise (right). Range [0°, 360°).

This module is a first-class navigation subsystem — the navigator must call
normalize() before each route and rotate() between walk segments. Heading
uncertainty above _HIGH_UNCERTAINTY should trigger a re-normalize.

Public API:
    cam = get_camera()
    cam.normalize(stop_event)        # F reset + optical flow settle
    cam.rotate(n)                    # n > 0 = right (.), n < 0 = left (,)
    cam.refine_from_flow(dx, dy, speed)  # update heading from optical flow
    h, unc = cam.heading, cam.heading_uncertainty
    cam.is_settled(frame)            # True when flow is calm
"""
from __future__ import annotations

import math
import threading
import time
from typing import Optional

from detection.screen_capture import get_screen_capture
from movement.position_detector import PositionDetector
from utils.logger import get_logger

log = get_logger(__name__)

# --- Timing ---
_SETTLE_TIME   = 0.60   # seconds to wait after F reset before measuring flow
_STABLE_SPEED  = 15.0   # px/s below which camera is considered stable
_MAX_WAIT      = 2.5    # max seconds to wait for stability
_RESET_PRESSES = 2      # number of 'f' presses per normalize

# --- Camera rotation model ---
_DEGREES_PER_TAP  = 15.0   # estimated heading change per . or , press in BSS
_ROTATE_DELAY     = 0.08   # seconds between consecutive taps

# --- Heading uncertainty ---
_INITIAL_UNCERTAINTY = 180.0  # completely unknown before first reset
_POST_RESET_UNCERTAINTY = 8.0  # after a clean F reset
_UNCERTAINTY_PER_TAP = 2.0    # each camera tap adds this much uncertainty
_HIGH_UNCERTAINTY   = 45.0    # above this: re-normalize before sensitive movement
_FLOW_REFINE_WEIGHT = 0.25    # max fractional correction per optical flow sample
_MIN_SPEED_FOR_REFINE = 20.0  # px/s below which flow heading is unreliable
_MAX_CORRECTION_DEG  = 50.0   # reject flow corrections larger than this (noise)


class CameraAligner:
    """
    Manages camera reset, heading estimation, and stability checks.

    Heading is estimated, not directly observed. Confidence comes from
    combining known reset state, rotation counts, and optical flow direction.

    Not thread-safe — call from the navigation thread only.
    """

    def __init__(self) -> None:
        self._sc       = get_screen_capture()
        self._detector = PositionDetector()
        self._heading: float = 0.0
        self._uncertainty: float = _INITIAL_UNCERTAINTY
        self._last_normalize: float = 0.0

    # ------------------------------------------------------------------ #
    # Heading model                                                        #
    # ------------------------------------------------------------------ #

    @property
    def heading(self) -> float:
        """Estimated camera heading in degrees [0°, 360°). 0° = post-reset forward."""
        return self._heading

    @property
    def heading_uncertainty(self) -> float:
        """Degrees of uncertainty in the heading estimate. Lower = more confident."""
        return self._uncertainty

    @property
    def heading_known(self) -> bool:
        """True when heading estimate is reliable enough for alignment decisions."""
        return self._uncertainty < _HIGH_UNCERTAINTY

    def refine_from_flow(self, dx: float, dy: float, speed: float) -> None:
        """
        Use optical flow vector (dx, dy in px/s) to refine the heading estimate.

        dx > 0 = player moving right on screen (camera facing right)
        dy < 0 = player moving up on screen (camera facing forward)

        Only useful when speed is significant and uncertainty is not extreme.
        Call this every tick during forward movement for continuous refinement.
        """
        if speed < _MIN_SPEED_FOR_REFINE:
            return
        if self._uncertainty > 120.0:
            return  # too uncertain — flow refinement could send us further wrong

        # Screen flow → world heading: when pressing W (forward), flow goes up-screen.
        # A rightward camera means flow goes upper-left, etc.
        # atan2(dx, -dy): dx=right, -dy=up → 0° when moving straight up (forward)
        measured = math.degrees(math.atan2(dx, -dy)) % 360

        diff = (measured - self._heading + 180.0) % 360.0 - 180.0  # signed [-180, 180]

        if abs(diff) > _MAX_CORRECTION_DEG:
            # Optical flow disagrees strongly — likely noise, partial occlusion, or jump
            self._uncertainty = min(90.0, self._uncertainty * 1.05)
            return

        weight = min(_FLOW_REFINE_WEIGHT, speed / 400.0)
        self._heading = (self._heading + weight * diff) % 360.0
        # Reduce uncertainty proportionally to the confidence of this sample
        self._uncertainty = max(3.0, self._uncertainty * (1.0 - weight * 0.4))

    # ------------------------------------------------------------------ #
    # Control                                                              #
    # ------------------------------------------------------------------ #

    def normalize(self, stop_event: threading.Event) -> bool:
        """
        Reset camera to default behind-player view and wait for it to settle.
        Updates heading estimate to 0° with low uncertainty.

        Returns True when stable (or after timeout), False if stop_event set.
        """
        if stop_event.is_set():
            return False

        self._reset_camera()
        self._detector.reset()

        settled = self._wait_for_settle(stop_event)

        if settled:
            self._heading = 0.0
            self._uncertainty = _POST_RESET_UNCERTAINTY
            self._last_normalize = time.monotonic()
            log.debug("Camera: normalized — heading=0° uncertainty=%.1f°", self._uncertainty)

        return settled

    def rotate(self, n: int) -> None:
        """
        Rotate camera horizontally.
        n > 0 → rotate right ('.' key × n), n < 0 → rotate left (',' key × |n|).
        Updates heading model.
        """
        if n == 0:
            return
        key = "." if n > 0 else ","
        try:
            from execution.input_interface import get_input
            inp = get_input()
            for _ in range(abs(n)):
                inp.tap_key(key)
                time.sleep(_ROTATE_DELAY)
        except Exception as exc:
            log.debug("Camera rotate error: %s", exc)

        self._heading = (self._heading + n * _DEGREES_PER_TAP) % 360.0
        self._uncertainty = min(60.0, self._uncertainty + abs(n) * _UNCERTAINTY_PER_TAP)
        log.debug("Camera: rotate(%+d) → heading=%.1f° unc=%.1f°",
                  n, self._heading, self._uncertainty)

    def align_to_heading(
        self,
        target_deg: float,
        stop_event: threading.Event,
        tolerance: float = 12.0,
    ) -> bool:
        """
        Rotate camera until the heading estimate is within tolerance of target_deg.

        Call before a walk segment to pre-align the camera so that movement
        keys map to the expected world directions.

        Returns True when aligned (or already within tolerance).
        Returns False if stop_event is set.

        tolerance: acceptable angular error in degrees.
        """
        if stop_event.is_set():
            return False

        # Signed angular difference in [-180, 180]
        diff = (target_deg - self._heading + 180.0) % 360.0 - 180.0

        if abs(diff) <= tolerance:
            log.debug("Camera: already aligned (heading=%.1f° target=%.1f°)",
                      self._heading, target_deg)
            return True

        taps = round(diff / _DEGREES_PER_TAP)
        if taps == 0:
            return True

        log.debug("Camera: align %.1f° → %.1f° (%+d taps)", self._heading, target_deg, taps)
        self.rotate(taps)

        if stop_event.is_set():
            return False

        # One corrective micro-tap if still outside tolerance and heading is reliable
        remaining = (target_deg - self._heading + 180.0) % 360.0 - 180.0
        if abs(remaining) > tolerance and self._uncertainty < 25.0:
            correction = round(remaining / _DEGREES_PER_TAP)
            if correction != 0:
                log.debug("Camera: corrective %+d tap(s) (remaining=%.1f°)", correction, remaining)
                self.rotate(correction)

        final_diff = abs((target_deg - self._heading + 180.0) % 360.0 - 180.0)
        aligned = final_diff <= tolerance + _UNCERTAINTY_PER_TAP * abs(taps)
        log.debug("Camera: align complete heading=%.1f° uncertainty=%.1f° aligned=%s",
                  self._heading, self._uncertainty, aligned)
        return aligned

    def is_settled(self, frame=None) -> bool:
        """Check whether the camera is currently stable (low optical flow)."""
        if frame is None:
            frame = self._sc.capture_full()
        if frame is None:
            return True
        d = self._detector.push_frame(frame)
        return d is None or d.speed < _STABLE_SPEED

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    def _reset_camera(self) -> None:
        try:
            from execution.input_interface import get_input
            inp = get_input()
            for _ in range(_RESET_PRESSES):
                inp.tap_key("f")
                time.sleep(0.12)
        except Exception as exc:
            log.debug("Camera reset error: %s", exc)

    def _wait_for_settle(self, stop_event: threading.Event) -> bool:
        time.sleep(_SETTLE_TIME)
        t0 = time.monotonic()
        while time.monotonic() - t0 < _MAX_WAIT:
            if stop_event.is_set():
                return False
            frame = self._sc.capture_full()
            if frame is not None:
                d = self._detector.push_frame(frame)
                if d is None or d.speed < _STABLE_SPEED:
                    return True
            time.sleep(0.08)
        log.debug("Camera: settle timeout — proceeding anyway")
        return True


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[CameraAligner] = None
_inst_lock = threading.Lock()


def get_camera() -> CameraAligner:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = CameraAligner()
    return _instance
