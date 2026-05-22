"""
Relative coordinate system.

Stores positions as fractions (0.0–1.0) of the Roblox window rather
than absolute pixel values.  At runtime, fractions are multiplied by
the current window size so the macro adapts to window moves/resizes
and different screen resolutions without recalibration.

Storage format in coordinates.json:
  {
    "hive": {"rel_x": 0.42, "rel_y": 0.31, "anchor": "roblox_window",
             "abs_x": 850, "abs_y": 620}
  }

abs_x/abs_y are the original capture-time values kept for debugging.
anchor is always "roblox_window" for game coordinates, or "screen" for
coordinates relative to the full display (e.g. the hive UI overlay).
"""
import json
import threading
from pathlib import Path
from typing import Optional

from calibration.roblox_finder import roblox_bounds_or_screen, get_roblox_bounds
from utils.logger import get_logger

log = get_logger(__name__)

_COORDS_FILE = Path(__file__).parent.parent / "config" / "coordinates.json"
_lock = threading.Lock()


# ── Storage ──────────────────────────────────────────────────────────────

def save_relative(name: str, abs_x: int, abs_y: int) -> dict:
    """
    Convert absolute screen coordinates to relative, save, and return the entry.
    Automatically determines the anchor from Roblox window bounds.
    """
    bounds = get_roblox_bounds()
    if bounds and bounds["width"] > 0 and bounds["height"] > 0:
        rel_x = (abs_x - bounds["left"]) / bounds["width"]
        rel_y = (abs_y - bounds["top"])  / bounds["height"]
        anchor = "roblox_window"
    else:
        # Fall back to screen-relative
        try:
            import mss
            with mss.mss() as sct:
                m = sct.monitors[1]
                sw, sh = m["width"], m["height"]
        except Exception:
            sw, sh = 1920, 1080
        rel_x = abs_x / sw
        rel_y = abs_y / sh
        anchor = "screen"

    entry = {
        "rel_x":  round(rel_x, 5),
        "rel_y":  round(rel_y, 5),
        "anchor": anchor,
        "abs_x":  abs_x,
        "abs_y":  abs_y,
    }

    coords = _load()
    coords[name] = entry
    _save(coords)
    log.info("Saved '%s': rel=(%.3f, %.3f) abs=(%d, %d)", name, rel_x, rel_y, abs_x, abs_y)
    return entry


def resolve(name: str) -> Optional[tuple[int, int]]:
    """
    Resolve a named coordinate to current absolute (x, y) screen pixels.
    Returns None if the coordinate hasn't been recorded.
    """
    coords = _load()
    entry = coords.get(name)
    if entry is None:
        return None

    # Legacy format (plain {"x": N, "y": N})
    if "x" in entry and "rel_x" not in entry:
        return int(entry["x"]), int(entry["y"])

    rel_x = entry.get("rel_x", 0.0)
    rel_y = entry.get("rel_y", 0.0)
    anchor = entry.get("anchor", "roblox_window")

    if anchor == "roblox_window":
        bounds = roblox_bounds_or_screen()
        abs_x = int(bounds["left"] + rel_x * bounds["width"])
        abs_y = int(bounds["top"]  + rel_y * bounds["height"])
    else:
        try:
            import mss
            with mss.mss() as sct:
                m = sct.monitors[1]
                abs_x = int(rel_x * m["width"])
                abs_y = int(rel_y * m["height"])
        except Exception:
            abs_x = int(rel_x * 1920)
            abs_y = int(rel_y * 1080)

    return abs_x, abs_y


def resolve_region(region_cfg: dict) -> dict:
    """
    Given a region config that may be stored as relative fractions,
    return an absolute {"left", "top", "width", "height"} dict.
    """
    if region_cfg.get("rel_width") is not None:
        bounds = roblox_bounds_or_screen()
        return {
            "left":   int(bounds["left"] + region_cfg["rel_left"]  * bounds["width"]),
            "top":    int(bounds["top"]  + region_cfg["rel_top"]   * bounds["height"]),
            "width":  int(region_cfg["rel_width"]  * bounds["width"]),
            "height": int(region_cfg["rel_height"] * bounds["height"]),
        }
    return region_cfg


def list_coordinates() -> dict:
    return _load()


def delete_coordinate(name: str) -> bool:
    coords = _load()
    if name in coords:
        del coords[name]
        _save(coords)
        return True
    return False


def _load() -> dict:
    with _lock:
        if _COORDS_FILE.exists():
            try:
                with open(_COORDS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


def _save(data: dict) -> None:
    with _lock:
        _COORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_COORDS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
