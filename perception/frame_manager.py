"""
FrameManager — single-capture-per-tick shared frame pipeline.

Every detector that needs the current screen calls get_frame_manager()
instead of touching ScreenCapture directly. The first caller in each tick
triggers exactly one MSS grab; all subsequent callers within the same TTL
window get the cached result with zero overhead.

Architecture rule:
    During the runtime loop, FrameManager is the ONLY code that calls
    ScreenCapture.capture_full(). Detectors receive frames from here.

Cache invalidation:
    - Automatic: cache expires after _CACHE_TTL seconds (≈ 30 fps max)
    - Manual: invalidate() forces a fresh capture on the next access

Named region crops:
    region("backpack_pct") → crops from screen.regions.backpack_pct in config
    Crops are cached separately and invalidated whenever the full frame refreshes.

Public API:
    fm = get_frame_manager()
    bgr  = fm.full_frame()            # BGR ndarray or None
    gray = fm.full_gray()             # grayscale, same capture
    crop = fm.region("backpack_pct")  # BGR crop of a named config region
    fm.invalidate()                   # force refresh on next call
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np

from detection.screen_capture import get_screen_capture
from config.config_manager import get_config
from utils.logger import get_logger

log = get_logger(__name__)

# Maximum cache age before a new MSS grab is triggered (seconds)
_CACHE_TTL = 0.033   # ≈ 30 fps upper bound; navigation ticks run at ~22 fps


@dataclass
class _FrameCache:
    bgr:  np.ndarray
    gray: Optional[np.ndarray] = field(default=None, compare=False)
    ts:   float = 0.0


class FrameManager:
    """
    Shared screen-frame pipeline.

    Thread-safe via RLock — the same thread can call full_frame() and
    full_gray() in sequence without deadlock.
    """

    def __init__(self) -> None:
        self._sc    = get_screen_capture()
        self._lock  = threading.RLock()
        self._cache: Optional[_FrameCache] = None
        # region name → (crop_array, capture_timestamp)
        self._region_cache: Dict[str, Tuple[np.ndarray, float]] = {}

    # ------------------------------------------------------------------ #
    # Full-frame access                                                    #
    # ------------------------------------------------------------------ #

    def full_frame(self, max_age: float = _CACHE_TTL) -> Optional[np.ndarray]:
        """
        Return the current full BGR frame.
        Triggers a new MSS grab only if the cached frame is older than max_age.
        """
        with self._lock:
            self._refresh(max_age)
            return self._cache.bgr if self._cache else None

    def full_gray(self, max_age: float = _CACHE_TTL) -> Optional[np.ndarray]:
        """
        Return a grayscale copy of the current full frame.
        Reuses the cached BGR → avoids a second MSS call and a redundant
        color-space conversion on the same tick.
        """
        with self._lock:
            self._refresh(max_age)
            if self._cache is None:
                return None
            if self._cache.gray is None:
                try:
                    import cv2
                    self._cache.gray = cv2.cvtColor(self._cache.bgr, cv2.COLOR_BGR2GRAY)
                except Exception as exc:
                    log.debug("Grayscale conversion failed: %s", exc)
            return self._cache.gray

    # ------------------------------------------------------------------ #
    # Named region crops                                                   #
    # ------------------------------------------------------------------ #

    def region(self, name: str, max_age: float = _CACHE_TTL) -> Optional[np.ndarray]:
        """
        Return a cached BGR crop of a named config region
        (config key: screen.regions.<name>).

        Returns None if the region is not configured or has zero dimensions.
        """
        with self._lock:
            now = time.monotonic()

            # Return cached crop if still fresh
            cached = self._region_cache.get(name)
            if cached is not None and (now - cached[1]) <= max_age:
                return cached[0]

            cfg = get_config()
            reg = cfg.get(f"screen.regions.{name}", None)
            if not reg or reg.get("width", 0) == 0:
                return None

            self._refresh(max_age)
            if self._cache is None:
                return None

            left = int(reg.get("left", 0))
            top  = int(reg.get("top",  0))
            w    = int(reg.get("width",  0))
            h    = int(reg.get("height", 0))

            fh, fw = self._cache.bgr.shape[:2]
            left = max(0, min(left, fw - 1))
            top  = max(0, min(top,  fh - 1))
            w    = min(w, fw - left)
            h    = min(h, fh - top)
            if w <= 0 or h <= 0:
                return None

            # .copy() ensures the crop is independent of the parent array
            crop = self._cache.bgr[top:top + h, left:left + w].copy()
            self._region_cache[name] = (crop, self._cache.ts)
            return crop

    def region_direct(
        self,
        left: int,
        top: int,
        w: int,
        h: int,
        max_age: float = _CACHE_TTL,
    ) -> Optional[np.ndarray]:
        """
        Crop by explicit pixel coordinates (logical / non-Retina pixels).
        Use when a fixed HUD element is known at design time.
        """
        with self._lock:
            self._refresh(max_age)
            if self._cache is None:
                return None

            fh, fw = self._cache.bgr.shape[:2]
            left = max(0, min(left, fw - 1))
            top  = max(0, min(top,  fh - 1))
            w    = min(w, fw - left)
            h    = min(h, fh - top)
            if w <= 0 or h <= 0:
                return None
            return self._cache.bgr[top:top + h, left:left + w].copy()

    # ------------------------------------------------------------------ #
    # Cache control                                                        #
    # ------------------------------------------------------------------ #

    def invalidate(self) -> None:
        """Force a fresh MSS capture on the very next access."""
        with self._lock:
            self._cache = None
            self._region_cache.clear()

    @property
    def frame_age(self) -> float:
        """Seconds elapsed since the last successful full capture."""
        with self._lock:
            if self._cache is None:
                return float("inf")
            return time.monotonic() - self._cache.ts

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    def _refresh(self, max_age: float) -> None:
        """Perform a new MSS grab if the cache is absent or expired. Holds lock."""
        now = time.monotonic()
        if self._cache is not None and (now - self._cache.ts) <= max_age:
            return

        bgr = self._sc.capture_full()
        if bgr is not None:
            self._cache = _FrameCache(bgr=bgr, ts=now)
            self._region_cache.clear()


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[FrameManager] = None
_inst_lock = threading.Lock()


def get_frame_manager() -> FrameManager:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = FrameManager()
    return _instance
