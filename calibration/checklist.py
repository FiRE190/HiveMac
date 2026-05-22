"""
Calibration status checker.
Returns structured status for every required calibration item so the
main window and wizard can show green/red indicators without duplicating logic.
"""
import json
from pathlib import Path
from typing import NamedTuple

_ROOT = Path(__file__).parent.parent
_COORDS_FILE   = _ROOT / "config" / "coordinates.json"
_SETTINGS_FILE = _ROOT / "config" / "settings.json"
_TEMPLATES_DIR = _ROOT / "templates"

# Items the macro cannot function without
REQUIRED_COORDS = [
    ("hive",          "Hive entrance"),
    ("wealth_clock",  "Wealth Clock location"),
]

REQUIRED_TEMPLATES = [
    ("hive_ui.png",            "Hive conversion prompt"),
    ("respawn_screen.png",     "Death / respawn overlay"),
    ("wealth_clock_prompt.png","Wealth Clock activate prompt"),
]

REQUIRED_OCR_REGIONS = [
    ("backpack_pct", "Backpack percentage display"),
]

# At least one field coordinate must exist
KNOWN_FIELD_KEYS = [
    "sunflower_field", "dandelion_field", "mushroom_field",
    "blue_flower_field", "clover_field", "spider_field",
    "strawberry_field", "bamboo_field", "pineapple_patch",
    "stump_field", "cactus_field", "rose_field",
    "pepper_patch", "pine_tree_forest", "pumpkin_patch",
    "mountain_top_flower",
]


class CheckItem(NamedTuple):
    key: str
    label: str
    category: str   # "coordinate" | "template" | "ocr"
    ok: bool
    detail: str     # short human-readable status


def get_checklist() -> list[CheckItem]:
    coords   = _load_json(_COORDS_FILE)
    settings = _load_json(_SETTINGS_FILE)
    regions  = settings.get("screen", {}).get("regions", {})

    items: list[CheckItem] = []

    # ---- Coordinates ----
    for key, label in REQUIRED_COORDS:
        ok = key in coords and isinstance(coords[key], dict)
        items.append(CheckItem(
            key=key, label=label, category="coordinate",
            ok=ok,
            detail=f"({coords[key]['x']}, {coords[key]['y']})" if ok else "not recorded",
        ))

    # At least one field
    field_keys = [k for k in KNOWN_FIELD_KEYS if k in coords]
    has_field  = len(field_keys) > 0
    items.append(CheckItem(
        key="__field__", label="At least one field location", category="coordinate",
        ok=has_field,
        detail=f"{len(field_keys)} recorded" if has_field else "none recorded",
    ))

    # ---- Templates ----
    for filename, label in REQUIRED_TEMPLATES:
        path = _TEMPLATES_DIR / filename
        ok   = path.exists() and path.stat().st_size > 0
        items.append(CheckItem(
            key=filename, label=label, category="template",
            ok=ok,
            detail="captured" if ok else "missing",
        ))

    # ---- OCR regions ----
    for key, label in REQUIRED_OCR_REGIONS:
        region = regions.get(key, {})
        ok     = bool(region.get("width", 0) > 0 and region.get("height", 0) > 0)
        items.append(CheckItem(
            key=key, label=label, category="ocr",
            ok=ok,
            detail=f"{region['width']}×{region['height']}px" if ok else "not set",
        ))

    return items


def all_required_complete() -> bool:
    return all(item.ok for item in get_checklist())


def _load_json(path: Path) -> dict:
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}
