"""
MSS-based screen capture with Retina display scaling support.
All captured images are returned as BGR numpy arrays (OpenCV format).
"""
import subprocess
import threading
from typing import Optional

import mss
import mss.tools
import numpy as np

from config.config_manager import get_config
from utils.logger import get_logger

log = get_logger(__name__)


def _detect_scale_factor() -> float:
    """
    On Retina Macs, logical screen coords are half of physical pixel counts.
    We detect by comparing screencapture output dimensions vs mss dimensions.
    Falls back to config value if detection fails.
    """
    try:
        result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType"],
            capture_output=True, text=True, timeout=5
        )
        if "Retina" in result.stdout:
            return 2.0
    except Exception:
        pass
    cfg = get_config()
    return float(cfg.get("screen.scale_factor", 2.0))


class ScreenCapture:
    _instance: "ScreenCapture | None" = None
    _cls_lock = threading.Lock()

    def __new__(cls) -> "ScreenCapture":
        with cls._cls_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._scale_factor: float = _detect_scale_factor()
                inst._sct = mss.mss()
                log.info("ScreenCapture init: scale_factor=%.1f", inst._scale_factor)
                cls._instance = inst
        return cls._instance

    @property
    def scale_factor(self) -> float:
        return self._scale_factor

    def capture_full(self) -> np.ndarray:
        monitor = self._sct.monitors[1]  # primary display
        sct_img = self._sct.grab(monitor)
        frame = np.array(sct_img)
        return frame[:, :, :3]  # drop alpha, keep BGR

    def capture_region(self, region: dict) -> Optional[np.ndarray]:
        """
        region: {"left": int, "top": int, "width": int, "height": int}
        All values are in logical (non-retina) pixels.
        Returns None if region is unset (zero dimensions).
        """
        if region.get("width", 0) == 0 or region.get("height", 0) == 0:
            return None
        try:
            sct_img = self._sct.grab(region)
            frame = np.array(sct_img)
            return frame[:, :, :3]
        except Exception as e:
            log.warning("Screen capture region failed: %s", e)
            return None

    def capture_named_region(self, name: str) -> Optional[np.ndarray]:
        cfg = get_config()
        region = cfg.get(f"screen.regions.{name}", None)
        if region is None:
            log.debug("Region '%s' not calibrated", name)
            return None
        return self.capture_region(region)

    def logical_to_physical(self, x: int, y: int) -> tuple[int, int]:
        """Convert logical (pyautogui) coords to physical pixel coords."""
        return int(x * self._scale_factor), int(y * self._scale_factor)

    def physical_to_logical(self, x: int, y: int) -> tuple[int, int]:
        """Convert physical pixel coords to logical (pyautogui) coords."""
        return int(x / self._scale_factor), int(y / self._scale_factor)


def get_screen_capture() -> ScreenCapture:
    return ScreenCapture()
