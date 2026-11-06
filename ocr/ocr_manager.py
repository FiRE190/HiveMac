"""
OCR module — DISABLED.

pytesseract has been removed from this project.  All backpack / UI reading
now uses vision-based detection (HSV fill estimation, template matching,
contour analysis).

This stub preserves the public API so any file that still imports get_ocr()
continues to compile; all methods return empty / None values.

If you see this being called at runtime, trace the caller and replace it
with the appropriate visual detector:
    backpack_pct   → detection/backpack_detector.py
    death screen   → detection/death_detector.py
    hive state     → detection/hive_detector.py
"""
from __future__ import annotations

from typing import Optional
from utils.logger import get_logger

log = get_logger(__name__)


class OCRManager:
    """No-op OCR stub.  All methods log a warning and return empty values."""

    def read_region(self, region_name: str) -> str:
        log.warning("OCR disabled: read_region('%s') called — use visual detection", region_name)
        return ""

    def read_region_image(self, img) -> str:
        log.warning("OCR disabled: read_region_image() called — use visual detection")
        return ""

    def read_number(self, region_name: str) -> Optional[int]:
        log.warning("OCR disabled: read_number('%s') called — use visual detection", region_name)
        return None

    def read_number_from_image(self, img) -> Optional[int]:
        log.warning("OCR disabled: read_number_from_image() called — use visual detection")
        return None


_instance: Optional[OCRManager] = None


def get_ocr() -> OCRManager:
    global _instance
    if _instance is None:
        _instance = OCRManager()
    return _instance
