"""
Screen-based movement detection using Lucas-Kanade sparse optical flow.

The Roblox camera follows the player, so world-background features move
opposite to the player.  We negate the measured background flow to derive
the player's actual movement vector and speed in screen-pixels/second.

Usage:
    detector = PositionDetector()
    while running:
        frame = screen_capture.capture_full()
        delta = detector.push_frame(frame)
        if delta and delta.confidence > 0.3:
            print(f"speed={delta.speed:.1f} px/s")
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)

# Lucas-Kanade optical flow parameters
_LK_PARAMS = dict(
    winSize=(15, 15),
    maxLevel=2,
    criteria=(3, 10, 0.03),  # TERM_CRITERIA_EPS | TERM_CRITERIA_COUNT
)

# Shi-Tomasi corner detection parameters
_FEATURE_PARAMS = dict(maxCorners=80, qualityLevel=0.3, minDistance=7, blockSize=7)

# ROI: ignore outer 20% of frame — avoids HUD elements that don't move with the world
_ROI = (0.20, 0.20, 0.80, 0.80)  # (x0_frac, y0_frac, x1_frac, y1_frac)

# Below this many tracked features the measurement is considered unreliable
_MIN_FEATURES = 5


@dataclass
class MovementDelta:
    """Result of optical-flow computation between two consecutive frames."""
    dx:         float = 0.0   # player horizontal displacement (px/s); positive = right
    dy:         float = 0.0   # player vertical displacement (px/s);   positive = down
    speed:      float = 0.0   # magnitude of dx/dy (px/s)
    confidence: float = 0.0   # 0–1; based on number of successfully tracked features
    elapsed:    float = 0.0   # wall-clock seconds between the two frames


class PositionDetector:
    """
    Tracks world-background motion between consecutive screen frames.

    Not thread-safe — create one instance per farming session and call
    push_frame() from a single thread.  Call reset() after position jumps
    (hive return, death respawn, task switches).
    """

    def __init__(self) -> None:
        self._prev_gray: Optional[np.ndarray] = None
        self._prev_pts:  Optional[np.ndarray] = None
        self._prev_time: float = 0.0

    def push_frame(self, frame: np.ndarray) -> Optional[MovementDelta]:
        """
        Accept a new BGR frame.

        Returns a MovementDelta measured since the previous call, or None if
        this is the first frame or cv2 is unavailable.
        """
        try:
            import cv2
        except ImportError:
            return None

        now  = time.monotonic()
        h, w = frame.shape[:2]

        x0 = int(w * _ROI[0])
        y0 = int(h * _ROI[1])
        x1 = int(w * _ROI[2])
        y1 = int(h * _ROI[3])
        roi = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)

        delta: Optional[MovementDelta] = None

        if self._prev_gray is not None and self._prev_pts is not None:
            elapsed = max(now - self._prev_time, 1e-6)
            delta = self._compute_flow(self._prev_gray, roi, self._prev_pts, elapsed)

        pts = cv2.goodFeaturesToTrack(roi, mask=None, **_FEATURE_PARAMS)
        self._prev_gray = roi
        self._prev_pts  = pts
        self._prev_time = now

        return delta

    def reset(self) -> None:
        """Discard history.  Call after position jumps so stale flow isn't used."""
        self._prev_gray = None
        self._prev_pts  = None
        self._prev_time = 0.0

    # ------------------------------------------------------------------ #

    def _compute_flow(
        self,
        prev: np.ndarray,
        curr: np.ndarray,
        pts: np.ndarray,
        elapsed: float,
    ) -> MovementDelta:
        import cv2

        delta = MovementDelta(elapsed=elapsed)

        if pts is None or len(pts) == 0:
            return delta

        next_pts, status, _ = cv2.calcOpticalFlowPyrLK(prev, curr, pts, None, **_LK_PARAMS)
        if next_pts is None:
            return delta

        good_prev = pts[status == 1]
        good_next = next_pts[status == 1]

        if len(good_prev) < _MIN_FEATURES:
            return delta

        # Background displacement (median over all tracked features)
        flow    = good_next - good_prev
        bg_dx   = float(np.median(flow[:, 0]))
        bg_dy   = float(np.median(flow[:, 1]))

        # Player moves opposite to background shift
        delta.dx         = -bg_dx / elapsed
        delta.dy         = -bg_dy / elapsed
        delta.speed      = float(np.hypot(bg_dx, bg_dy)) / elapsed
        delta.confidence = min(1.0, len(good_prev) / 30.0)

        return delta


class FieldBoundaryDetector:
    """
    Detects when the player is approaching a field edge by comparing color
    histograms between the center of the frame and four thin edge strips.

    Each BSS field has a distinct color palette; terrain changes appear at
    the screen edges before the player physically exits the field.
    """

    SIMILARITY_THRESHOLD = 0.45  # correlation below this → terrain boundary

    def is_near_boundary(self, frame: np.ndarray) -> Tuple[bool, str]:
        """
        Returns (is_near_boundary, direction).
        direction is "up", "down", "left", "right", or "none".
        """
        try:
            import cv2
        except ImportError:
            return False, "none"

        h, w = frame.shape[:2]
        center      = frame[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4]
        center_hist = self._hist(center, cv2)

        strips = {
            "up":    frame[: h // 8,             w // 4 : 3 * w // 4],
            "down":  frame[7 * h // 8 :,         w // 4 : 3 * w // 4],
            "left":  frame[h // 4 : 3 * h // 4,  : w // 8],
            "right": frame[h // 4 : 3 * h // 4,  7 * w // 8 :],
        }

        for direction, strip in strips.items():
            if strip.size == 0:
                continue
            sim = cv2.compareHist(center_hist, self._hist(strip, cv2), cv2.HISTCMP_CORREL)
            if sim < self.SIMILARITY_THRESHOLD:
                log.debug("Field boundary detected on %s side (sim=%.2f)", direction, sim)
                return True, direction

        return False, "none"

    def _hist(self, region: np.ndarray, cv2) -> np.ndarray:
        hsv  = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [18, 16], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        return hist
