"""
Adaptive hybrid movement controller — real-time closed-loop feedback.

This is NOT a scripted macro:

  - Never holds a key for a fixed, pre-computed duration.
  - Every burst is adaptive: shorter when the player is boosted,
    longer when slowed, and immediately corrected on overshoot or drift.
  - Field boundary detection redirects the player before they exit.
  - Stuck detection triggers a recovery jump+strafe sequence.

Farming pattern key sequences are defined here rather than as (dx,dy) path
plans, because the adaptive controller owns all movement timing.

Public API:
    ac = AdaptiveController()
    for key, weight in ac.pattern_cycle("circular"):
        result = ac.step(key, weight, stop_event)
"""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Generator, Optional

from detection.screen_capture import get_screen_capture
from movement.position_detector import FieldBoundaryDetector, MovementDelta, PositionDetector
from movement.speed_calibrator import SpeedCalibrator
from utils.logger import get_logger

log = get_logger(__name__)

# ── Timing constants ───────────────────────────────────────────────────────────

BURST_BASE   = 0.18   # nominal burst at base speed (seconds)
BURST_MIN    = 0.08   # never shorter
BURST_MAX    = 0.35   # never longer (safety cap)
CAPTURE_TICK = 0.04   # screen capture during a burst (~25 fps)

# ── Thresholds ─────────────────────────────────────────────────────────────────

OVERSHOOT_RATIO = 1.30   # speed > 130% of base → apply counter-burst
STUCK_RATIO     = 0.05   # speed < 5% of base → stuck
MAX_STUCK_STEPS = 3      # consecutive stuck steps before recovery

# ── WASD geometry ──────────────────────────────────────────────────────────────

_OPPOSITE     = {"w": "s", "s": "w", "a": "d", "d": "a"}
_PERPENDICULAR = {
    "w": ["d", "a"],
    "s": ["a", "d"],
    "a": ["w", "s"],
    "d": ["s", "w"],
}

# ── Pattern → (key, relative_duration_weight) sequences ───────────────────────
# The controller multiplies BURST_BASE by each weight before speed-ratio scaling.
# Larger weight = longer burst in that direction = more distance covered.

_PATTERNS: dict[str, list[tuple[str, float]]] = {
    "circular":        [("w", 1.0), ("d", 1.0), ("s", 1.0), ("a", 1.0)],
    "zig-zag":         [("w", 2.0), ("d", 0.6), ("w", 2.0), ("a", 0.6)],
    "zigzag":          [("w", 2.0), ("d", 0.6), ("w", 2.0), ("a", 0.6)],
    "spiral":          [("w", 1.0), ("d", 1.5), ("s", 1.0), ("a", 1.5)],
    "corner":          [("w", 2.5), ("d", 2.5), ("s", 2.5), ("a", 2.5)],
    "corner_rotation": [("w", 2.5), ("d", 2.5), ("s", 2.5), ("a", 2.5)],
    "waypoint":        [("w", 1.0), ("d", 1.0), ("s", 1.0), ("a", 1.0)],
}
_DEFAULT_PATTERN = [("w", 1.0), ("d", 1.0), ("s", 1.0), ("a", 1.0)]


@dataclass
class StepResult:
    """Result of one adaptive movement step."""
    key:         str
    burst_dur:   float
    speed_ratio: float
    was_stuck:   bool   = False
    corrected:   bool   = False
    confidence:  float  = 0.0


class AdaptiveController:
    """
    Real-time closed-loop movement controller.

    Instantiate once per farming session.  Call reset() after the player
    teleports (hive return, respawn) so stale optical-flow data is discarded.

    Example:
        ac = AdaptiveController()
        for key, weight in ac.pattern_cycle("zig-zag"):
            if stop_event.is_set():
                break
            ac.step(key, weight, stop_event)
    """

    def __init__(self) -> None:
        self._sc         = get_screen_capture()
        self._detector   = PositionDetector()
        self._boundary   = FieldBoundaryDetector()
        self._calibrator = SpeedCalibrator()
        self._stuck_count = 0

    # ------------------------------------------------------------------ #
    # Speed calibration                                                    #
    # ------------------------------------------------------------------ #

    def calibrate_speed(self, stop_event: threading.Event) -> float:
        """Measure baseline movement speed.  Returns px/s (0 on failure)."""
        return self._calibrator.calibrate(stop_event)

    def get_base_speed(self) -> float:
        return self._calibrator.get_base_speed()

    # ------------------------------------------------------------------ #
    # Pattern cycling                                                      #
    # ------------------------------------------------------------------ #

    def pattern_cycle(self, pattern_name: str) -> Generator[tuple[str, float], None, None]:
        """
        Infinite generator of (key, weight) tuples for a named pattern.

        Typical usage:
            for key, weight in ac.pattern_cycle("circular"):
                result = ac.step(key, weight, stop_event)
                if stop_event.is_set():
                    break
        """
        key_name  = pattern_name.lower().replace(" ", "_")
        sequence  = _PATTERNS.get(key_name, _DEFAULT_PATTERN)
        idx = 0
        while True:
            yield sequence[idx % len(sequence)]
            idx += 1

    # ------------------------------------------------------------------ #
    # Single adaptive step                                                 #
    # ------------------------------------------------------------------ #

    def step(
        self,
        key: str,
        weight: float,
        stop_event: threading.Event,
    ) -> StepResult:
        """
        Execute one adaptive movement burst.

        Steps:
          1. Redirect if near a field boundary
          2. Sample current speed (2 frames)
          3. Compute burst_dur = (BURST_BASE × weight) / speed_ratio
          4. Hold key for burst_dur while sampling optical flow
          5. Evaluate result: stuck / overshoot / ok
          6. Apply counter-burst on overshoot; trigger recovery on stuck

        Returns StepResult with diagnostic data.
        """
        # 1. Boundary check — may redirect to a different key
        key = self._boundary_redirect(key)

        # 2. Pre-burst speed sample
        pre_speed = self._sample_speed(n=2)
        ratio     = self._calibrator.speed_ratio(pre_speed)

        # 3. Adaptive burst duration
        if ratio > 0.1:
            duration = (BURST_BASE * weight) / ratio
        else:
            # Uncalibrated or player is stationary — use base duration
            duration = BURST_BASE * weight
        duration = max(BURST_MIN, min(BURST_MAX, duration))

        # 4. Execute burst
        delta      = self._burst(key, duration, stop_event)
        confidence = delta.confidence if delta else 0.0

        # 5. Evaluate
        was_stuck = False
        corrected = False
        base      = self._calibrator.get_base_speed()

        if delta and delta.confidence > 0.2 and base > 0:
            if delta.speed < base * STUCK_RATIO:
                was_stuck = True
                self._stuck_count += 1
                log.debug("Stuck step %d/%d (speed=%.1f, base=%.1f)",
                          self._stuck_count, MAX_STUCK_STEPS, delta.speed, base)

                if self._stuck_count >= MAX_STUCK_STEPS:
                    self._recover_stuck(stop_event)
                    self._stuck_count = 0
                    self._detector.reset()

            elif delta.speed > base * OVERSHOOT_RATIO:
                self._counter_burst(key, delta.speed, base, stop_event)
                corrected = True
                self._stuck_count = 0

            else:
                self._stuck_count = 0
        else:
            # Can't measure (no cv2 or first frame) — reset stuck counter
            self._stuck_count = 0

        return StepResult(
            key=key,
            burst_dur=duration,
            speed_ratio=ratio,
            was_stuck=was_stuck,
            corrected=corrected,
            confidence=confidence,
        )

    def reset(self) -> None:
        """Discard optical-flow history and reset stuck counter.
        Call after teleports (hive return, respawn)."""
        self._detector.reset()
        self._stuck_count = 0

    # ------------------------------------------------------------------ #
    # Internal: burst execution                                            #
    # ------------------------------------------------------------------ #

    def _burst(
        self,
        key: str,
        duration: float,
        stop_event: threading.Event,
    ) -> Optional[MovementDelta]:
        """
        Hold key for duration seconds, sampling optical flow continuously.
        Returns the most recent MovementDelta, or None if unavailable.
        """
        try:
            import pyautogui
        except ImportError:
            return None

        last_delta: Optional[MovementDelta] = None
        t0 = time.monotonic()

        pyautogui.keyDown(key)
        try:
            while time.monotonic() - t0 < duration:
                if stop_event.is_set():
                    break
                frame = self._sc.capture_full()
                if frame is not None:
                    d = self._detector.push_frame(frame)
                    if d is not None:
                        last_delta = d
                time.sleep(CAPTURE_TICK)
        finally:
            pyautogui.keyUp(key)

        return last_delta

    def _counter_burst(
        self,
        original_key: str,
        actual_speed: float,
        base_speed: float,
        stop_event: threading.Event,
    ) -> None:
        """Apply a brief reverse burst to compensate for overshoot."""
        if stop_event.is_set():
            return
        excess_ratio = (actual_speed - base_speed) / base_speed
        dur = min(BURST_MIN, BURST_BASE * excess_ratio * 0.4)
        if dur > 0.02:
            opp = _OPPOSITE[original_key]
            log.debug("Counter-burst: key=%s dur=%.3fs (overshoot=%.0f%%)",
                      opp, dur, excess_ratio * 100)
            self._burst(opp, dur, stop_event)

    # ------------------------------------------------------------------ #
    # Internal: boundary redirection                                       #
    # ------------------------------------------------------------------ #

    def _boundary_redirect(self, key: str) -> str:
        """
        Sample the current frame.  If the player is heading toward a field
        edge, redirect to a perpendicular direction.
        """
        frame = self._sc.capture_full()
        if frame is None:
            return key

        near, edge_dir = self._boundary.is_near_boundary(frame)
        if not near:
            return key

        edge_key = {"up": "w", "down": "s", "left": "a", "right": "d"}.get(edge_dir, "")
        if edge_key == key:
            perps   = _PERPENDICULAR.get(key, ["d", "a"])
            new_key = random.choice(perps)
            log.debug("Boundary on %s → %s → %s", edge_dir, key, new_key)
            return new_key

        return key

    # ------------------------------------------------------------------ #
    # Internal: speed sampling                                             #
    # ------------------------------------------------------------------ #

    def _sample_speed(self, n: int = 2) -> float:
        """Capture n frames and return mean optical-flow speed (px/s)."""
        speeds: list[float] = []
        for _ in range(n):
            frame = self._sc.capture_full()
            if frame is not None:
                d = self._detector.push_frame(frame)
                if d and d.confidence > 0.2:
                    speeds.append(d.speed)
            time.sleep(CAPTURE_TICK)
        return float(sum(speeds) / len(speeds)) if speeds else 0.0

    # ------------------------------------------------------------------ #
    # Internal: stuck recovery                                             #
    # ------------------------------------------------------------------ #

    def _recover_stuck(self, stop_event: threading.Event) -> None:
        """
        Escape a stuck state: jump, random strafe, jump again.
        Resets optical-flow history so stale wall-contact frames are discarded.
        """
        log.info("Stuck recovery: jump + strafe (after %d consecutive stuck steps)",
                 MAX_STUCK_STEPS)
        try:
            import pyautogui
            pyautogui.press("space")
            time.sleep(0.15)
            if not stop_event.is_set():
                strafe = random.choice(["a", "d"])
                self._burst(strafe, 0.25, stop_event)
                pyautogui.press("space")
                time.sleep(0.25)
        except Exception as exc:
            log.debug("Stuck recovery error: %s", exc)
        log.info("Stuck recovery complete")
