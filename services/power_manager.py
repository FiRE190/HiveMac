"""
macOS power management: brightness control and caffeinate (prevent sleep).
Uses osascript for brightness (no extra deps) and subprocess caffeinate.
"""
import subprocess
import threading
from typing import Optional

from utils.logger import get_logger

log = get_logger(__name__)

_CAFFEINATE_CMD = ["caffeinate", "-d"]


class PowerManager:
    def __init__(self) -> None:
        self._original_brightness: Optional[int] = None
        self._caffeinate_proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Brightness                                                           #
    # ------------------------------------------------------------------ #

    def get_brightness(self) -> Optional[int]:
        """Returns current display brightness 0-100 via osascript, or None if unavailable."""
        try:
            result = subprocess.run(
                ["osascript", "-e", "tell application \"System Events\" to get brightness of (first desktop)"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                return int(float(result.stdout.strip()) * 100)
        except Exception as e:
            log.debug("get_brightness failed: %s", e)

        # Try brightness CLI (requires separate install)
        try:
            result = subprocess.run(
                ["brightness", "-l"], capture_output=True, text=True, timeout=3
            )
            for line in result.stdout.splitlines():
                if "brightness" in line.lower():
                    parts = line.split()
                    for p in parts:
                        try:
                            return int(float(p) * 100)
                        except ValueError:
                            pass
        except Exception:
            pass

        return None

    def set_brightness(self, level_pct: int) -> bool:
        """Set brightness to level_pct (0-100). Returns True on success."""
        level_pct = max(0, min(100, level_pct))
        normalized = level_pct / 100.0

        # Try osascript first
        script = f'tell application "System Events" to set brightness of (first desktop) to {normalized}'
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                log.debug("Brightness set to %d%% via osascript", level_pct)
                return True
        except Exception as e:
            log.debug("osascript brightness failed: %s", e)

        # Try brightness CLI
        try:
            result = subprocess.run(
                ["brightness", str(normalized)],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                log.debug("Brightness set to %d%% via brightness CLI", level_pct)
                return True
        except Exception:
            pass

        log.warning("Could not set brightness to %d%%", level_pct)
        return False

    def reduce_brightness(self, target_pct: int = 30) -> None:
        with self._lock:
            self._original_brightness = self.get_brightness()
            self.set_brightness(target_pct)
            log.info("Brightness reduced to %d%% (was %s%%)", target_pct, self._original_brightness)

    def restore_brightness(self) -> None:
        with self._lock:
            if self._original_brightness is not None:
                self.set_brightness(self._original_brightness)
                log.info("Brightness restored to %d%%", self._original_brightness)
                self._original_brightness = None

    # ------------------------------------------------------------------ #
    # Caffeinate (prevent display / system sleep)                         #
    # ------------------------------------------------------------------ #

    def caffeinate_start(self) -> None:
        with self._lock:
            if self._caffeinate_proc is not None:
                return
            try:
                self._caffeinate_proc = subprocess.Popen(
                    _CAFFEINATE_CMD,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                log.info("caffeinate started (pid=%d)", self._caffeinate_proc.pid)
            except FileNotFoundError:
                log.warning("caffeinate not found (not macOS?)")

    def caffeinate_stop(self) -> None:
        with self._lock:
            if self._caffeinate_proc:
                self._caffeinate_proc.terminate()
                self._caffeinate_proc = None
                log.info("caffeinate stopped")
