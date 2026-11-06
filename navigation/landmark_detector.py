"""
Landmark detector — visual identification of BSS world features.

Detection strategy (no OCR):
  1. Template matching  — if a .png template exists in templates/landmarks/
  2. HSV color profile  — each landmark has a characteristic color signature
  3. Score fusion       — max(template_conf, color_conf * 0.85)

The detector intentionally avoids returning False positives at the cost of
missing True positives — a low-confidence sighting is ignored.  The localizer
handles the probability integration.

Public API:
    det = get_landmark_detector()
    readings = det.scan(frame, names=["hive_exterior", "red_cannon"])
    best     = det.strongest(readings)
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from navigation.types import LandmarkReading
from utils.logger import get_logger

log = get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "landmarks"

# Minimum fused confidence to emit a reading (below → silently ignored)
_EMIT_THRESHOLD = 0.40


# ─────────────────────────────────────────────────────────────────────────────
# Landmark color profiles
#
# Each profile is (H_low, H_high, S_min, V_min, min_coverage_fraction).
# Coverage = fraction of the *detection zone* (see _DETECT_ZONE) that
# matches the HSV range.  Values are OpenCV: H 0-180, S/V 0-255.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _ColorProfile:
    h_low:  int
    h_high: int
    s_min:  int = 60
    v_min:  int = 60
    min_coverage: float = 0.04   # 4% of detection zone must match


# Detection zone for color matching: central 60% of frame (ignores HUD edges)
_DETECT_ZONE = (0.20, 0.15, 0.80, 0.85)   # x0_frac, y0_frac, x1_frac, y1_frac

# Landmark HSV color profiles
_COLOR_PROFILES: Dict[str, _ColorProfile] = {
    # Hive: golden amber hexagonal structures
    "hive_exterior": _ColorProfile(h_low=15, h_high=35, s_min=100, v_min=100, min_coverage=0.03),
    # Spawn platform: sandy/wooden tan
    "spawn_platform": _ColorProfile(h_low=18, h_high=30, s_min=50,  v_min=100, min_coverage=0.05),
    # Red cannon: saturated red
    "red_cannon":    _ColorProfile(h_low=0,  h_high=8,  s_min=150, v_min=100, min_coverage=0.02),
    # Mushroom: brown-red cap with white spots (brown stem)
    "mushroom_platform": _ColorProfile(h_low=0, h_high=12, s_min=80, v_min=60, min_coverage=0.03),
    # Sunflowers: vivid yellow
    "sunflower_field": _ColorProfile(h_low=22, h_high=38, s_min=160, v_min=140, min_coverage=0.06),
    # Dandelion: white (low saturation, high value)
    "dandelion_field": _ColorProfile(h_low=0, h_high=180, s_min=0, v_min=200, min_coverage=0.08),
    # Bamboo: vivid green
    "bamboo_field":  _ColorProfile(h_low=38, h_high=75, s_min=100, v_min=80, min_coverage=0.06),
    # Clover: medium green
    "clover_field":  _ColorProfile(h_low=38, h_high=75, s_min=80, v_min=80, min_coverage=0.07),
    # Blue flowers: blue-purple
    "blue_flower_field": _ColorProfile(h_low=100, h_high=140, s_min=80, v_min=80, min_coverage=0.05),
    # Strawberry: vivid red (same hue as red cannon, different coverage pattern)
    "strawberry_field": _ColorProfile(h_low=0, h_high=10, s_min=140, v_min=80, min_coverage=0.05),
    # Stump: dark brown wood grain
    "stump_field":   _ColorProfile(h_low=8, h_high=22, s_min=60, v_min=40, min_coverage=0.06),
    # Rose: vivid red with green stems
    "rose_field":    _ColorProfile(h_low=0, h_high=10, s_min=130, v_min=70, min_coverage=0.04),
    # Pineapple: yellow-green
    "pineapple_patch": _ColorProfile(h_low=28, h_high=50, s_min=80, v_min=100, min_coverage=0.04),
    # Pine tree: dark green
    "pine_tree_forest": _ColorProfile(h_low=40, h_high=70, s_min=60, v_min=40, min_coverage=0.07),
    # Spider field: dark purple/grey ground
    "spider_field":  _ColorProfile(h_low=130, h_high=160, s_min=30, v_min=30, min_coverage=0.06),
}


class LandmarkDetector:
    """
    Detects BSS landmarks in a single BGR frame.

    Thread-safe (template cache uses a lock; frame processing is stateless).
    """

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._template_cache: Dict[str, Optional[np.ndarray]] = {}

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def scan(
        self,
        frame: np.ndarray,
        names: Optional[List[str]] = None,
    ) -> List[LandmarkReading]:
        """
        Scan frame for one or more named landmarks.

        names=None → scan for all registered landmarks.
        Returns readings above _EMIT_THRESHOLD, sorted by confidence desc.
        """
        if names is None:
            names = list(_COLOR_PROFILES.keys())

        readings: List[LandmarkReading] = []
        for name in names:
            r = self._detect_one(frame, name)
            if r is not None:
                readings.append(r)

        readings.sort(key=lambda r: r.confidence, reverse=True)
        return readings

    def strongest(
        self,
        readings: List[LandmarkReading],
        min_conf: float = _EMIT_THRESHOLD,
    ) -> Optional[LandmarkReading]:
        for r in readings:
            if r.confidence >= min_conf:
                return r
        return None

    def available_landmarks(self) -> List[str]:
        return list(_COLOR_PROFILES.keys())

    # ------------------------------------------------------------------ #
    # Per-landmark detection                                               #
    # ------------------------------------------------------------------ #

    def _detect_one(self, frame: np.ndarray, name: str) -> Optional[LandmarkReading]:
        try:
            import cv2
        except ImportError:
            return None

        template_conf, template_rect = self._template_match(frame, name, cv2)
        color_conf, color_rect       = self._color_match(frame, name, cv2)

        # Fuse: template is more reliable when available
        if template_conf > 0.0 and color_conf > 0.0:
            fused = max(template_conf, color_conf * 0.85)
            rect  = template_rect if template_conf >= color_conf else color_rect
        elif template_conf > 0.0:
            fused = template_conf
            rect  = template_rect
        else:
            fused = color_conf * 0.85   # penalize color-only for FP risk
            rect  = color_rect

        if fused < _EMIT_THRESHOLD:
            return None

        return LandmarkReading(name=name, confidence=round(fused, 3), screen_rect=rect)

    # ------------------------------------------------------------------ #
    # Template matching                                                    #
    # ------------------------------------------------------------------ #

    def _load_template(self, name: str) -> Optional[np.ndarray]:
        with self._lock:
            if name in self._template_cache:
                return self._template_cache[name]

        path = _TEMPLATE_DIR / f"{name}.png"
        tmpl: Optional[np.ndarray] = None
        if path.exists():
            try:
                import cv2
                raw  = cv2.imread(str(path))
                tmpl = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY) if raw is not None else None
            except Exception as exc:
                log.debug("Template load failed %s: %s", name, exc)

        with self._lock:
            self._template_cache[name] = tmpl
        return tmpl

    def _template_match(
        self,
        frame: np.ndarray,
        name: str,
        cv2,
    ) -> Tuple[float, Tuple[int, int, int, int]]:
        tmpl = self._load_template(name)
        if tmpl is None:
            return 0.0, (0, 0, 0, 0)

        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            th, tw = tmpl.shape[:2]
            fh, fw = gray.shape[:2]
            if th > fh or tw > fw:
                return 0.0, (0, 0, 0, 0)

            result = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            x, y = max_loc
            return float(max_val), (x, y, tw, th)
        except Exception as exc:
            log.debug("Template match error %s: %s", name, exc)
            return 0.0, (0, 0, 0, 0)

    # ------------------------------------------------------------------ #
    # HSV color matching                                                   #
    # ------------------------------------------------------------------ #

    def _color_match(
        self,
        frame: np.ndarray,
        name: str,
        cv2,
    ) -> Tuple[float, Tuple[int, int, int, int]]:
        profile = _COLOR_PROFILES.get(name)
        if profile is None:
            return 0.0, (0, 0, 0, 0)

        try:
            h, w = frame.shape[:2]
            x0 = int(w * _DETECT_ZONE[0])
            y0 = int(h * _DETECT_ZONE[1])
            x1 = int(w * _DETECT_ZONE[2])
            y1 = int(h * _DETECT_ZONE[3])
            zone = frame[y0:y1, x0:x1]

            hsv   = cv2.cvtColor(zone, cv2.COLOR_BGR2HSV)
            lower = np.array([profile.h_low, profile.s_min, profile.v_min])
            upper = np.array([profile.h_high, 255, 255])
            mask  = cv2.inRange(hsv, lower, upper)

            coverage = float(np.count_nonzero(mask)) / mask.size
            if coverage < profile.min_coverage:
                return 0.0, (0, 0, 0, 0)

            # Normalize coverage into [0, 1] with saturation at 3× min_coverage
            conf = min(1.0, coverage / (profile.min_coverage * 3.0))

            # Bounding rect of the matching pixels for rough screen_rect
            pts = cv2.findNonZero(mask)
            if pts is not None:
                rx, ry, rw, rh = cv2.boundingRect(pts)
                rect = (x0 + rx, y0 + ry, rw, rh)
            else:
                rect = (x0, y0, x1 - x0, y1 - y0)

            return conf, rect
        except Exception as exc:
            log.debug("Color match error %s: %s", name, exc)
            return 0.0, (0, 0, 0, 0)

    # ------------------------------------------------------------------ #
    # Template cache management                                            #
    # ------------------------------------------------------------------ #

    def invalidate(self, name: Optional[str] = None) -> None:
        """Invalidate cached template(s) — call after capturing new templates."""
        with self._lock:
            if name:
                self._template_cache.pop(name, None)
            else:
                self._template_cache.clear()


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[LandmarkDetector] = None
_inst_lock = threading.Lock()


def get_landmark_detector() -> LandmarkDetector:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = LandmarkDetector()
    return _instance
