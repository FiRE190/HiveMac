"""
Death/respawn detection via template matching.
Template file: templates/respawn_screen.png (captured during calibration).
"""
from detection.screen_capture import get_screen_capture
from detection.template_matcher import match_template
from config.config_manager import get_config
from utils.logger import get_logger

log = get_logger(__name__)


def is_dead() -> bool:
    """
    Returns True if the Roblox respawn/death screen is detected.
    Requires templates/respawn_screen.png to be captured via calibration.
    """
    cfg = get_config()
    threshold = cfg.get("detection.death_screen_threshold", 0.85)

    sc = get_screen_capture()
    screen = sc.capture_full()

    found, _, conf = match_template(screen, "respawn_screen.png", threshold)
    if found:
        log.warning("Death detected (confidence=%.2f)", conf)
    return found
