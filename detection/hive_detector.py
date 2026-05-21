"""
Detects proximity to or interaction with the hive.
Template: templates/hive_ui.png (the collect/convert pollen UI prompt).
"""
from detection.screen_capture import get_screen_capture
from detection.template_matcher import match_template
from config.config_manager import get_config
from utils.logger import get_logger

log = get_logger(__name__)


def is_at_hive() -> bool:
    """Returns True if the hive conversion UI is visible on screen."""
    cfg = get_config()
    threshold = cfg.get("detection.hive_threshold", 0.80)
    sc = get_screen_capture()
    screen = sc.capture_full()
    found, _, conf = match_template(screen, "hive_ui.png", threshold)
    if found:
        log.debug("Hive UI detected (conf=%.2f)", conf)
    return found


def is_hive_converting() -> bool:
    """Returns True if pollen conversion animation/progress is visible."""
    sc = get_screen_capture()
    screen = sc.capture_full()
    found, _, _ = match_template(screen, "hive_converting.png", 0.78)
    return found
