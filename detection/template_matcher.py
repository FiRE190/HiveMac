"""
OpenCV template matching with multi-scale support for Retina displays.
Returns (found, center_xy, confidence) for any template search.
"""
import os
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _load_template(template_name: str) -> Optional[np.ndarray]:
    """Load template by filename from the templates/ directory."""
    path = _TEMPLATES_DIR / template_name
    if not path.exists():
        log.debug("Template not found: %s", path)
        return None
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        log.warning("Failed to read template: %s", path)
    return img


def match_template(
    screen: np.ndarray,
    template_name: str,
    threshold: float = 0.80,
    multi_scale: bool = True,
) -> tuple[bool, Optional[tuple[int, int]], float]:
    """
    Search screen for template_name (file in templates/).

    Returns:
        (found, (cx, cy) in logical pixels, confidence)
    """
    template = _load_template(template_name)
    if template is None:
        return False, None, 0.0

    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    tpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

    best_val = 0.0
    best_loc = None
    best_w, best_h = tpl_gray.shape[1], tpl_gray.shape[0]

    scales = [1.0, 0.75, 0.5, 1.25] if multi_scale else [1.0]

    for scale in scales:
        th = max(1, int(tpl_gray.shape[0] * scale))
        tw = max(1, int(tpl_gray.shape[1] * scale))
        resized = cv2.resize(tpl_gray, (tw, th))

        if resized.shape[0] > screen_gray.shape[0] or resized.shape[1] > screen_gray.shape[1]:
            continue

        result = cv2.matchTemplate(screen_gray, resized, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val > best_val:
            best_val = max_val
            best_loc = max_loc
            best_w, best_h = tw, th

    if best_val >= threshold and best_loc is not None:
        cx = best_loc[0] + best_w // 2
        cy = best_loc[1] + best_h // 2
        return True, (cx, cy), best_val

    return False, None, best_val


def match_any(
    screen: np.ndarray,
    template_names: list[str],
    threshold: float = 0.80,
) -> tuple[bool, Optional[str], Optional[tuple[int, int]], float]:
    """
    Check multiple templates and return the first match found.
    Returns (found, matched_name, center_xy, confidence).
    """
    for name in template_names:
        found, loc, conf = match_template(screen, name, threshold)
        if found:
            return True, name, loc, conf
    return False, None, None, 0.0
