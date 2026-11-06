"""
Find the Roblox window with Quartz (CGWindowListCopyWindowInfo). Unlike the
AppleScript route this needs no Accessibility permission, works for a full
screen window, and costs a millisecond.

Window mode (config game.window_mode):
  windowed    the macro reads the content area, which is the window minus the
              title bar (config game.title_bar_height, default 28 points)
  fullscreen  the window covers the display, nothing is subtracted; turn the
              menu bar's "auto hide in full screen" on so it does not overlap

All rectangles are in points, the unit mss and pynput share.
"""
from __future__ import annotations

import subprocess
from typing import Iterable, Optional

from utils.logger import get_logger

log = get_logger(__name__)

OWNER_HINT = "roblox"


def pick_window(infos: Iterable[dict], owner_hint: str = OWNER_HINT) -> Optional[dict]:
    """Largest normal (layer 0) window whose owner name contains the hint.
    `infos` are CGWindowListCopyWindowInfo dictionaries. Pure, so it is tested."""
    best: Optional[dict] = None
    best_area = 0
    for w in infos:
        owner = str(w.get("kCGWindowOwnerName", "")).lower()
        if owner_hint.lower() not in owner or w.get("kCGWindowLayer", 0) != 0:
            continue
        b = w.get("kCGWindowBounds") or {}
        width, height = int(b.get("Width", 0)), int(b.get("Height", 0))
        if width < 100 or height < 100:
            continue
        if width * height > best_area:
            best_area = width * height
            best = {"left": int(b.get("X", 0)), "top": int(b.get("Y", 0)), "width": width, "height": height}
    return best


def content_rect(window: dict, mode: str, title_bar: int) -> dict:
    """Window rect to the rect the macro reads. Pure."""
    if mode == "fullscreen":
        return dict(window)
    t = max(0, min(int(title_bar), window["height"] // 4))
    return {"left": window["left"], "top": window["top"] + t, "width": window["width"], "height": window["height"] - t}


def list_windows() -> list[dict]:
    try:
        import Quartz
        opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        return list(Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or [])
    except Exception as exc:
        log.debug("window list failed: %s", exc)
        return []


def get_roblox_bounds(force_refresh: bool = False, owner_hint: str = OWNER_HINT) -> Optional[dict]:
    """Raw Roblox window rect, or None. `force_refresh` is kept for callers; there is no cache
    because the lookup is cheap."""
    return pick_window(list_windows(), owner_hint)


def content_bounds(owner_hint: str = OWNER_HINT) -> Optional[dict]:
    """Roblox content rect for the configured window mode, or None."""
    from config.config_manager import get_config
    cfg = get_config()
    w = get_roblox_bounds(owner_hint=owner_hint)
    if w is None:
        return None
    return content_rect(w, str(cfg.get("game.window_mode", "windowed")), int(cfg.get("game.title_bar_height", 28)))


def is_roblox_running() -> bool:
    return get_roblox_bounds() is not None


def focus_roblox() -> bool:
    """Bring Roblox to the front (works for a full screen Space too)."""
    try:
        r = subprocess.run(["open", "-a", "Roblox"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False
