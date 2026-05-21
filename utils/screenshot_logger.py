"""
Saves annotated debug screenshots to the debug/ directory.
Called automatically on errors, watchdog timeouts, and emergency stops.
"""
import os
import time
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

log = get_logger(__name__)

_DEBUG_DIR = Path(__file__).parent.parent / "debug"


def log_error_screenshot(context: str = "error") -> Optional[str]:
    """
    Capture the current screen and save it to debug/<timestamp>_<context>.png.
    Returns the saved path, or None on failure.
    """
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{context}.png"
    path = _DEBUG_DIR / filename

    try:
        import mss
        import mss.tools
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(path))
        log.info("Screenshot saved: %s", path)
        return str(path)
    except Exception as e:
        log.warning("Screenshot failed: %s", e)

    # Fallback: try PIL
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        _annotate_and_save(img, path, context)
        log.info("Screenshot saved (PIL fallback): %s", path)
        return str(path)
    except Exception as e:
        log.warning("PIL screenshot fallback also failed: %s", e)

    return None


def _annotate_and_save(img, path: Path, context: str) -> None:
    """Add a timestamp and context label to the screenshot."""
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(img)
    label = f"{context}  {time.strftime('%Y-%m-%d %H:%M:%S')}"
    draw.rectangle([0, 0, len(label) * 7 + 10, 22], fill=(200, 0, 0, 180))
    draw.text((5, 4), label, fill=(255, 255, 255))
    img.save(str(path))
