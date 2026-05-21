"""
Detects the Wealth Clock activation prompt on screen.
Template: templates/wealth_clock_prompt.png
"""
from detection.screen_capture import get_screen_capture
from detection.template_matcher import match_template
from config.config_manager import get_config
from utils.logger import get_logger

log = get_logger(__name__)


def is_wealth_clock_visible() -> bool:
    """Returns True if the Wealth Clock activate prompt is on screen."""
    cfg = get_config()
    threshold = cfg.get("detection.template_match_threshold", 0.80)
    sc = get_screen_capture()
    screen = sc.capture_full()
    found, _, conf = match_template(screen, "wealth_clock_prompt.png", threshold)
    if found:
        log.debug("Wealth Clock detected (conf=%.2f)", conf)
    return found


def is_wealth_clock_active() -> bool:
    """Returns True if the Wealth Clock buff indicator is visible in the HUD."""
    sc = get_screen_capture()
    screen = sc.capture_full()
    found, _, _ = match_template(screen, "wealth_clock_active.png", 0.78)
    return found
