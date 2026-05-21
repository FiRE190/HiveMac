"""
pytesseract OCR wrapper with image preprocessing for reliable digit reading.
Call read_region() for text, read_number() for integer extraction.
"""
import re
from typing import Optional

import cv2
import numpy as np
import pytesseract

from detection.screen_capture import get_screen_capture
from utils.logger import get_logger

log = get_logger(__name__)

# Config: tesseract PSM 7 = single text line, 8 = single word, 13 = raw line
_PSM_LINE = "--psm 7 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz%/ "
_PSM_DIGIT = "--psm 7 -c tessedit_char_whitelist=0123456789%"


def _preprocess(img: np.ndarray, for_digits: bool = False) -> np.ndarray:
    """
    Convert to grayscale, upscale, threshold, and denoise for OCR accuracy.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Upscale small regions 3× for better OCR
    if gray.shape[0] < 60 or gray.shape[1] < 120:
        gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    # Adaptive threshold
    processed = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    # Light denoise
    processed = cv2.medianBlur(processed, 3)
    return processed


class OCRManager:
    def read_region(self, region_name: str) -> str:
        """Capture a named screen region and return OCR text."""
        sc = get_screen_capture()
        img = sc.capture_named_region(region_name)
        if img is None:
            return ""
        return self._run_ocr(img, digits_only=False)

    def read_region_image(self, img: np.ndarray) -> str:
        """Run OCR on a pre-captured image."""
        return self._run_ocr(img, digits_only=False)

    def read_number(self, region_name: str) -> Optional[int]:
        """Capture a named region and return the first integer found."""
        sc = get_screen_capture()
        img = sc.capture_named_region(region_name)
        if img is None:
            return None
        return self._run_ocr_number(img)

    def read_number_from_image(self, img: np.ndarray) -> Optional[int]:
        return self._run_ocr_number(img)

    def _run_ocr(self, img: np.ndarray, digits_only: bool = False) -> str:
        try:
            processed = _preprocess(img, for_digits=digits_only)
            config = _PSM_DIGIT if digits_only else _PSM_LINE
            text = pytesseract.image_to_string(processed, config=config)
            return text.strip()
        except Exception as e:
            log.warning("OCR error: %s", e)
            return ""

    def _run_ocr_number(self, img: np.ndarray) -> Optional[int]:
        text = self._run_ocr(img, digits_only=True)
        nums = re.findall(r"\d+", text)
        if nums:
            return int(nums[0])
        return None


_instance: Optional[OCRManager] = None


def get_ocr() -> OCRManager:
    global _instance
    if _instance is None:
        _instance = OCRManager()
    return _instance
