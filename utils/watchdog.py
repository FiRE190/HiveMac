"""
Watchdog: background thread that monitors the heartbeat timestamp.
If no heartbeat is received for watchdog_timeout_sec, it force-stops the macro.

Also registers the global emergency stop hotkey (default F9) via pynput.
"""
import threading
import time
from typing import Callable, Optional

from pynput import keyboard

from config.config_manager import get_config
from state.state_manager import get_state
from utils.logger import get_logger
from utils.screenshot_logger import log_error_screenshot

log = get_logger(__name__)


class Watchdog:
    def __init__(self, stop_callback: Callable) -> None:
        """
        stop_callback: called by the watchdog when the heartbeat times out.
                       Should be FarmingService.stop().
        """
        self._stop_callback = stop_callback
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._hotkey_listener: Optional[keyboard.GlobalHotKeys] = None

    def start(self) -> None:
        cfg = get_config()
        self._interval = cfg.get("timing.watchdog_interval_sec", 30)
        self._timeout = cfg.get("timing.watchdog_timeout_sec", 60)

        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="watchdog", daemon=True
        )
        self._thread.start()

        self._register_hotkey()
        log.info("Watchdog started (interval=%ds, timeout=%ds)", self._interval, self._timeout)

    def stop(self) -> None:
        self._running = False
        if self._hotkey_listener:
            self._hotkey_listener.stop()

    def _run(self) -> None:
        sm = get_state()
        idle_states = {"IDLE", "PAUSED", "ERROR"}

        while self._running:
            time.sleep(self._interval)
            if not self._running:
                break

            state = sm.current_state
            if state in idle_states:
                continue

            age = time.time() - sm.last_heartbeat
            if age > self._timeout:
                log.error(
                    "Watchdog: heartbeat stale (%.0fs old) in state %s — forcing stop",
                    age, state,
                )
                log_error_screenshot(context="watchdog_timeout")
                try:
                    self._stop_callback()
                except Exception as e:
                    log.error("Watchdog stop callback failed: %s", e)

    def _register_hotkey(self) -> None:
        cfg = get_config()
        key_str = cfg.get("app.emergency_stop_key", "f9")
        hotkey_map = {f"<{key_str}>": self._emergency_stop}

        try:
            self._hotkey_listener = keyboard.GlobalHotKeys(hotkey_map)
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()
            log.info("Emergency stop hotkey registered: %s", key_str)
        except Exception as e:
            log.warning("Could not register hotkey %s: %s", key_str, e)

    def _emergency_stop(self) -> None:
        log.warning("EMERGENCY STOP triggered via hotkey")
        log_error_screenshot(context="emergency_stop")
        try:
            self._stop_callback()
        except Exception as e:
            log.error("Emergency stop callback error: %s", e)
