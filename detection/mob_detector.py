"""
Mob detection: looks for mob HP bars or mob field indicator templates.
Templates: templates/mob_hp_bar.png, templates/mob_cleared.png
"""
from detection.screen_capture import get_screen_capture
from detection.template_matcher import match_template, match_any
from config.config_manager import get_config
from utils.logger import get_logger

log = get_logger(__name__)

_MOB_HP_TEMPLATES = ["mob_hp_bar.png", "mob_hp_bar_alt.png"]


def mobs_present() -> bool:
    """Returns True if any mob HP bar is visible on screen."""
    cfg = get_config()
    threshold = cfg.get("detection.mob_threshold", 0.78)
    sc = get_screen_capture()
    screen = sc.capture_full()
    found, _, _, _ = match_any(screen, _MOB_HP_TEMPLATES, threshold)
    if found:
        log.debug("Mobs detected on screen")
    return found


def mob_area_cleared() -> bool:
    """Returns True if the 'area cleared' or token drop template is visible."""
    sc = get_screen_capture()
    screen = sc.capture_full()
    found, _, _ = match_template(screen, "mob_cleared.png", 0.80)
    return found


def token_visible() -> bool:
    """Returns True if a loot token is visible on screen."""
    sc = get_screen_capture()
    screen = sc.capture_full()
    found, _, _ = match_template(screen, "loot_token.png", 0.78)
    return found
