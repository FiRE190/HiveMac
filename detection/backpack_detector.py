"""
Backpack pollen-fill detector — vision only, no OCR.

Strategy
--------
1. Capture the calibrated backpack region (screen.regions.backpack_pct).
2. Convert to HSV; isolate honey/amber fill pixels with a tuned color mask.
3. Fill ratio = matching_pixels / total_region_pixels.
4. Map fill ratio → 0–100% using a calibrated or default max-fill reference.
5. Apply EMA smoothing to suppress single-frame noise.
6. Return percentage + confidence so callers can decide to trust the reading.

Confidence is based on the fraction of bright (non-black) pixels in the region.
A dark/blank region (uncalibrated, Roblox not open) returns confidence ≈ 0.

Color profile — honey/pollen fill bar in BSS default graphics settings:
    Hue:        15–40   (golden amber)
    Saturation: 80–255
    Value:      80–255

If the default color profile does not match your graphics preset, adjust
detection.backpack_hsv_* in config or run the calibration tool.

Without a calibrated region the detector returns (0, confidence=0.0).
Run the calibration tool → Regions → backpack_pct to define the region.
"""
from __future__ import annotations

import threading
from typing import Optional, Tuple

import numpy as np

from config.config_manager import get_config
from utils.logger import get_logger

log = get_logger(__name__)

# ── Default HSV bounds for pollen fill ────────────────────────────────────────
_H_LOW  = 15
_H_HIGH = 40
_S_MIN  = 80
_V_MIN  = 80

# EMA smoothing factor  (higher = snappier, more noise; lower = smoother, slower)
_ALPHA = 0.35

# A region smaller than this is likely miscalibrated — skip it
_MIN_REGION_PX = 100

# Confidence floor required to emit a reading
_MIN_CONF = 0.10


class BackpackDetector:
    """
    Visual pollen fill estimator.

    Instantiate once per session.  Call from a single thread.
    Call reset() after teleports so the EMA doesn't carry stale data.
    """

    def __init__(self) -> None:
        self._smoothed: float     = 0.0
        self._has_first: bool     = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def get_pollen_pct(self) -> int:
        """
        Estimated backpack fill (0–100).
        Returns 0 when uncalibrated or confidence is too low.
        """
        raw, conf = self._measure()
        if conf < _MIN_CONF:
            return 0
        return self._smooth(raw)

    def get_pollen_pct_with_confidence(self) -> Tuple[int, float]:
        """Returns (pct, confidence) for callers that need the uncertainty."""
        raw, conf = self._measure()
        if conf < _MIN_CONF:
            return 0, 0.0
        return self._smooth(raw), round(conf, 3)

    def is_full(self, threshold: int = 90) -> bool:
        return self.get_pollen_pct() >= threshold

    def reset(self) -> None:
        """Discard smoothed history — call after teleports."""
        with self._lock:
            self._smoothed  = 0.0
            self._has_first = False

    # ------------------------------------------------------------------ #
    # Core measurement                                                     #
    # ------------------------------------------------------------------ #

    def _measure(self) -> Tuple[float, float]:
        """
        Returns (raw_pct, confidence).

        confidence 0.0 = uncalibrated or dark region.
        confidence 1.0 = strong, well-lit region reading.
        """
        try:
            import cv2
        except ImportError:
            return 0.0, 0.0

        region = self._capture_region()
        if region is None:
            return 0.0, 0.0

        h_r, w_r = region.shape[:2]
        total_px = h_r * w_r
        if total_px < _MIN_REGION_PX:
            return 0.0, 0.0

        cfg = get_config()

        # Allow per-profile HSV overrides
        h_low  = int(cfg.get("detection.backpack_hsv_h_low",  _H_LOW))
        h_high = int(cfg.get("detection.backpack_hsv_h_high", _H_HIGH))
        s_min  = int(cfg.get("detection.backpack_hsv_s_min",  _S_MIN))
        v_min  = int(cfg.get("detection.backpack_hsv_v_min",  _V_MIN))

        hsv   = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        lower = np.array([h_low,  s_min, v_min], dtype=np.uint8)
        upper = np.array([h_high, 255,   255],   dtype=np.uint8)
        mask  = cv2.inRange(hsv, lower, upper)

        fill_px    = int(np.count_nonzero(mask))
        fill_ratio = fill_px / total_px

        # Confidence: fraction of the region that is bright (not black screen)
        v_channel   = hsv[:, :, 2]
        bright_frac = float(np.count_nonzero(v_channel > 50)) / total_px
        confidence  = min(1.0, bright_frac * 1.5)

        # Map fill ratio → percentage using calibrated or default max fill
        max_fill = float(cfg.get("detection.backpack_max_fill_ratio", 0.40))
        if max_fill < 0.01:
            max_fill = 0.40

        pct = (fill_ratio / max_fill) * 100.0
        return max(0.0, min(100.0, pct)), confidence

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _smooth(self, raw: float) -> int:
        with self._lock:
            if not self._has_first:
                self._smoothed  = raw
                self._has_first = True
            else:
                self._smoothed = _ALPHA * raw + (1.0 - _ALPHA) * self._smoothed
        return max(0, min(100, round(self._smoothed)))

    def _capture_region(self):
        cfg = get_config()
        reg = cfg.get("screen.regions.backpack_pct", None)
        if not reg or reg.get("width", 0) == 0:
            return None
        from detection.screen_capture import get_screen_capture
        return get_screen_capture().capture_region(reg)


# ── Module-level convenience API ──────────────────────────────────────────────

_detector: Optional[BackpackDetector] = None
_det_lock  = threading.Lock()


def _get_detector() -> BackpackDetector:
    global _detector
    with _det_lock:
        if _detector is None:
            _detector = BackpackDetector()
    return _detector


def get_backpack_pct() -> int:
    """Returns pollen percentage (0–100)."""
    return _get_detector().get_pollen_pct()


def is_backpack_full(threshold: int = 90) -> bool:
    return _get_detector().is_full(threshold)
