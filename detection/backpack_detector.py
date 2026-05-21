"""
Reads current backpack pollen percentage from the screen using OCR.
Falls back to a safe value (0%) if the region is uncalibrated.
"""
from typing import Optional

from config.config_manager import get_config
from ocr.ocr_manager import get_ocr
from utils.logger import get_logger

log = get_logger(__name__)


def get_backpack_pct() -> int:
    """
    Returns the current backpack fill percentage (0-100).
    Returns 0 if the OCR region is not yet calibrated.
    """
    cfg = get_config()
    region = cfg.get("screen.regions.backpack_pct", None)
    if not region or region.get("width", 0) == 0:
        return 0

    ocr = get_ocr()
    value = ocr.read_number("backpack_pct")
    if value is None:
        return 0

    # Clamp to valid range
    return max(0, min(100, value))


def is_backpack_full(threshold: int = 90) -> bool:
    return get_backpack_pct() >= threshold
