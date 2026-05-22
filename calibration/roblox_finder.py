"""
Roblox window auto-detection for macOS.

Uses osascript (AppleScript) to find the Roblox process and its window
bounds.  Updates periodically so the macro adapts to window moves/resizes.

All other systems should call get_roblox_bounds() to get the current
window rect instead of using hardcoded screen positions.
"""
import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

log = get_logger(__name__)

_SETTINGS_PATH = Path(__file__).parent.parent / "config" / "settings.json"

# Cache so we don't run osascript on every detection call
_cache_lock = threading.Lock()
_cached_bounds: Optional[dict] = None
_last_check: float = 0.0
_CACHE_TTL = 5.0  # seconds


def get_roblox_bounds(force_refresh: bool = False) -> Optional[dict]:
    """
    Returns {"left": int, "top": int, "width": int, "height": int} in
    logical screen pixels, or None if Roblox is not running/detected.
    """
    global _cached_bounds, _last_check

    with _cache_lock:
        age = time.time() - _last_check
        if not force_refresh and age < _CACHE_TTL and _cached_bounds is not None:
            return _cached_bounds

    bounds = _detect_via_osascript()

    if bounds is None:
        bounds = _detect_via_mss_fallback()

    with _cache_lock:
        _cached_bounds = bounds
        _last_check = time.time()

    if bounds:
        _persist_bounds(bounds)
        log.debug("Roblox window: %s", bounds)
    else:
        log.debug("Roblox window not detected")

    return bounds


def _detect_via_osascript() -> Optional[dict]:
    """
    Ask System Events for the Roblox window position and size.
    Works on macOS without extra dependencies.
    """
    script = """
    try
        tell application "System Events"
            set robloxProcs to every process whose name contains "Roblox"
            if (count of robloxProcs) = 0 then return "not_found"
            set rp to item 1 of robloxProcs
            if (count of windows of rp) = 0 then return "no_window"
            set w to item 1 of windows of rp
            set {px, py} to position of w
            set {pw, ph} to size of w
            return (px as string) & "," & (py as string) & "," & (pw as string) & "," & (ph as string)
        end tell
    on error errMsg
        return "error:" & errMsg
    end try
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5,
        )
        out = result.stdout.strip()
        if out in ("not_found", "no_window") or out.startswith("error:"):
            return None
        parts = out.split(",")
        if len(parts) == 4:
            left, top, width, height = (int(p.strip()) for p in parts)
            if width > 100 and height > 100:
                return {"left": left, "top": top, "width": width, "height": height}
    except Exception as e:
        log.debug("osascript window detection error: %s", e)
    return None


def _detect_via_mss_fallback() -> Optional[dict]:
    """
    Fall back to persisted bounds from the last successful detection.
    """
    try:
        if _SETTINGS_PATH.exists():
            with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            w = data.get("screen", {}).get("roblox_window", {})
            if w.get("width", 0) > 100:
                return w
    except Exception:
        pass
    return None


def _persist_bounds(bounds: dict) -> None:
    """Save detected bounds to settings.json for fallback use."""
    try:
        data: dict = {}
        if _SETTINGS_PATH.exists():
            with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        data.setdefault("screen", {})["roblox_window"] = bounds
        with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.debug("Could not persist Roblox bounds: %s", e)


def is_roblox_running() -> bool:
    return get_roblox_bounds() is not None


def roblox_bounds_or_screen() -> dict:
    """
    Returns Roblox window bounds, falling back to the full primary monitor
    if Roblox isn't detected. Always returns a valid rect.
    """
    bounds = get_roblox_bounds()
    if bounds:
        return bounds
    try:
        import mss
        with mss.mss() as sct:
            m = sct.monitors[1]
            return {"left": m["left"], "top": m["top"],
                    "width": m["width"], "height": m["height"]}
    except Exception:
        return {"left": 0, "top": 0, "width": 1920, "height": 1080}


def focus_roblox() -> bool:
    """Bring the Roblox window to the front. Returns True on success."""
    script = """
    try
        tell application "Roblox" to activate
        return "ok"
    on error
        try
            tell application "System Events"
                set frontmost of (first process whose name contains "Roblox") to true
            end tell
            return "ok"
        on error errMsg
            return "error:" & errMsg
        end try
    end try
    """
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() == "ok"
    except Exception:
        return False
