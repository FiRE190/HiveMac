"""
Small region capture with mss. Returns RGB numpy arrays in the coordinate space
the rest of the app uses (points, as reported by the window finder). On a
Retina display mss returns twice as many pixels per point; `scale` records that
and `pixel()` samples the centre of the point so relative layouts stay valid.

Measured on an M series Mac: one small grab costs about 0.15 ms of CPU in this
process and 13 to 15 ms of wall time waiting for WindowServer. A few grabs per
second are negligible; a full screen grab in a tight loop is not, so nobody
here captures the full screen.
"""
from __future__ import annotations

import threading
from typing import Optional

import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)


class ScreenCapture:
    def __init__(self) -> None:
        import mss
        self._sct = mss.mss()
        self._lock = threading.Lock()
        self.scale = self._detect_scale()
        log.info("ScreenCapture ready, pixel scale %.1f", self.scale)

    def _detect_scale(self) -> float:
        try:
            img = self._sct.grab({"left": 0, "top": 0, "width": 20, "height": 20})
            return img.width / 20.0
        except Exception as exc:
            log.warning("scale detection failed: %s", exc)
            return 1.0

    def grab(self, region: dict) -> Optional[np.ndarray]:
        """region in points -> RGB array (H, W, 3) in device pixels."""
        if region.get("width", 0) <= 0 or region.get("height", 0) <= 0:
            return None
        try:
            with self._lock:
                img = self._sct.grab({k: int(region[k]) for k in ("left", "top", "width", "height")})
            arr = np.frombuffer(img.bgra, dtype=np.uint8).reshape(img.height, img.width, 4)
            return arr[:, :, [2, 1, 0]]
        except Exception as exc:
            log.warning("grab failed for %s: %s", region, exc)
            return None

    def pixel(self, x: int, y: int) -> Optional[tuple[int, int, int]]:
        """RGB of the point (x, y). Grabs a 1x1 point region and samples its centre."""
        arr = self.grab({"left": int(x), "top": int(y), "width": 1, "height": 1})
        if arr is None or arr.size == 0:
            return None
        cy, cx = arr.shape[0] // 2, arr.shape[1] // 2
        r, g, b = arr[cy, cx]
        return int(r), int(g), int(b)

    def save_png(self, region: dict, path: str) -> bool:
        try:
            import mss.tools
            with self._lock:
                img = self._sct.grab({k: int(region[k]) for k in ("left", "top", "width", "height")})
            mss.tools.to_png(img.rgb, img.size, output=path)
            return True
        except Exception as exc:
            log.warning("save_png failed: %s", exc)
            return False


_instance: Optional[ScreenCapture] = None
_lock = threading.Lock()


def get_screen_capture() -> ScreenCapture:
    global _instance
    with _lock:
        if _instance is None:
            _instance = ScreenCapture()
    return _instance
