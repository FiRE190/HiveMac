"""
Identifies the current field by matching templates for known BSS fields.
Templates are named: field_<sanitized_name>.png (e.g. field_sunflower_field.png).
"""
from typing import Optional

from detection.screen_capture import get_screen_capture
from detection.template_matcher import match_any
from config.config_manager import get_config
from navigation.node_names import field_display_names
from utils.logger import get_logger

log = get_logger(__name__)

# Only fields the nav map can route to. The list is derived from config/nav_map.json.
KNOWN_FIELDS = field_display_names() or [
    "Sunflower Field",
    "Dandelion Field",
    "Mushroom Field",
    "Blue Flower Field",
    "Clover Field",
    "Spider Field",
    "Strawberry Field",
    "Bamboo Field",
    "Pineapple Patch",
    "Stump Field",
    "Cactus Field",
    "Rose Field",
    "Pepper Patch",
    "Pine Tree Forest",
    "Pumpkin Patch",
    "Mountain Top Flower",
]


def _template_name(field: str) -> str:
    return "field_" + field.lower().replace(" ", "_") + ".png"


def get_current_field() -> Optional[str]:
    """
    Returns the name of the detected field, or None if unrecognized.
    """
    cfg = get_config()
    threshold = cfg.get("detection.template_match_threshold", 0.80)

    sc = get_screen_capture()
    screen = sc.capture_full()

    templates = [_template_name(f) for f in KNOWN_FIELDS]
    found, matched_template, _, conf = match_any(screen, templates, threshold)

    if found and matched_template:
        # Reverse-map template name back to field name
        for field in KNOWN_FIELDS:
            if _template_name(field) == matched_template:
                log.debug("Field detected: %s (conf=%.2f)", field, conf)
                return field

    return None
