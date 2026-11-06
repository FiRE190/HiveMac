"""Saves a debug screenshot of the Roblox window (or the screen) to debug/."""
import time
from typing import Optional

from utils import appdirs
from utils.logger import get_logger

log = get_logger(__name__)

_DEBUG_DIR = appdirs.debug_dir()


def log_error_screenshot(context: str = "error") -> Optional[str]:
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    path = _DEBUG_DIR / f"{time.strftime('%Y%m%d_%H%M%S')}_{context}.png"
    try:
        from calibration.roblox_finder import content_bounds as get_roblox_bounds
        from detection.screen_capture import get_screen_capture
        region = get_roblox_bounds()
        cap = get_screen_capture()
        if not region:
            import mss
            with mss.mss() as sct:
                region = dict(sct.monitors[1])
        if cap.save_png(region, str(path)):
            log.info("Screenshot saved: %s", path)
            return str(path)
    except Exception as exc:
        log.warning("Screenshot failed: %s", exc)
    return None
