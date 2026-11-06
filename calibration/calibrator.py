"""
Calibration actions shared by the Calibrate tab: everything that writes the
`hud` section of the config or saves a template. No UI here, so the pieces are
small and testable where they do not touch the screen.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from calibration.layout import RelPoint, RelRegion, WindowBounds, natro_defaults
from config.config_manager import get_config
from utils.logger import get_logger

log = get_logger(__name__)
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

ADJUST = [
    ("backpack_pixel", "Backpack pixel"),
    ("health_pixel", "Health pixel"),
    ("hive_prompt", "Hive prompt"),
    ("hive_view", "Hive view"),
]


def current_window() -> Optional[WindowBounds]:
    from calibration.roblox_finder import content_bounds
    b = content_bounds()
    if not b or b.get("width", 0) < 100:
        return None
    cfg = get_config()
    cfg.set("screen.roblox_window", b)
    cfg.save()
    return WindowBounds(int(b["left"]), int(b["top"]), int(b["width"]), int(b["height"]))


def seed_defaults(w: WindowBounds) -> None:
    cfg = get_config()
    for key, val in natro_defaults(w).items():
        if cfg.get(f"hud.{key}") in (None, {}):
            cfg.set(f"hud.{key}", val)
    cfg.save()


def save_point(key: str, x: int, y: int, w: WindowBounds) -> dict:
    cfg = get_config()
    d = RelPoint.from_absolute(x, y, w).to_dict()
    cfg.set(f"hud.{key}", d)
    cfg.save()
    log.info("saved %s at %s", key, d)
    return d


def save_region(key: str, region: dict, w: WindowBounds) -> dict:
    cfg = get_config()
    d = RelRegion.from_absolute(region, w).to_dict()
    cfg.set(f"hud.{key}", d)
    cfg.save()
    log.info("saved %s as %s", key, d)
    return d


def save_template(name: str, region: dict) -> bool:
    from detection.screen_capture import get_screen_capture
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    ok = get_screen_capture().save_png(region, str(TEMPLATES_DIR / name))
    if ok:
        log.info("template %s saved from %s", name, region)
    return ok


def template_exists(name: str) -> bool:
    return bool(name) and (TEMPLATES_DIR / name).exists()


def status() -> dict[str, bool]:
    cfg = get_config()
    hud = cfg.get_section("hud")
    return {
        "window": bool(cfg.get("screen.roblox_window", {}).get("width", 0) > 100),
        "backpack_pixel": bool(hud.get("backpack_pixel")),
        "health_pixel": bool(hud.get("health_pixel")),
        "hive_prompt": bool(hud.get("hive_prompt_region")) and template_exists(hud.get("hive_prompt_template", "")),
        "hive_view": bool(hud.get("hive_view_region")) and template_exists(hud.get("hive_view_template", "")),
        "paths": True,
    }


def required_complete() -> bool:
    """Only the window is required; Detect also fills in Natro's default spots."""
    return status()["window"]


def describe_readings(present: bool, rgb, raw, filtered: int, health_grey: bool, prompt, view) -> list[str]:
    """Plain language verdicts for the live panel. Pure, so it is tested."""
    if not present:
        return ["Roblox window: NOT FOUND. Open Roblox in a window."]
    out = ["Roblox window: found"]
    if rgb is None:
        out.append("Backpack: cannot read the screen. Check Screen Recording permission.")
    elif raw is None:
        out.append(f"Backpack: colour {rgb} is not a bar colour. Use Adjust > Backpack pixel.")
    else:
        out.append(f"Backpack: {filtered}% (looks right if it matches the bar)")
    out.append("Health: dead" if health_grey else "Health: alive")
    out.append("Hive prompt: " + ("not set up (optional)" if prompt is None else ("seen" if prompt else "not visible")))
    out.append("Hive view: " + ("not set up (optional)" if view is None else ("seen" if view else "not visible")))
    return out
