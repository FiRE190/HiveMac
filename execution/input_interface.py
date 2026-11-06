"""
InputInterface — the ONLY file in the codebase that imports pyautogui.

Enforcement: run `grep -r "import pyautogui" . | grep -v input_interface.py`
to verify no other file bypasses this layer.

Design:
  - All key presses, holds, and taps flow through this interface.
  - Tracks currently held keys so release_all() is always safe.
  - Exposes actual elapsed time from press_key() for closed-loop feedback.
  - Human jitter is opt-in and applied at this layer only.
  - PAUSE = 0 and FAILSAFE = False are set once here, not per-call.
"""
from __future__ import annotations

import random
import threading
import time
from typing import Optional

from utils.logger import get_logger

log = get_logger(__name__)

_WASD = ("w", "a", "s", "d")
_ALL_MOVEMENT = (*_WASD, "space", "q", "e", "f", "r")


class InputInterface:
    """
    Sole owner of pyautogui.  Thread-safe for release_all(); press_key()
    and tap_key() should only be called from one thread (the execution thread).
    """

    def __init__(self, jitter_ms: float = 10.0) -> None:
        self._jitter_ms = jitter_ms
        self._held: set[str] = set()
        self._held_lock = threading.Lock()
        self._paused = threading.Event()   # set → block all input

        try:
            import pyautogui as _pg
            _pg.PAUSE    = 0
            _pg.FAILSAFE = False
            self._pg = _pg
            self._available = True
        except ImportError:
            log.warning("InputInterface: pyautogui not available — input is simulated")
            self._pg = None
            self._available = False

    # ------------------------------------------------------------------ #
    # Core input methods                                                   #
    # ------------------------------------------------------------------ #

    def press_key(self, key: str, duration: float, *, jitter: bool = True) -> float:
        """
        Hold `key` for `duration` seconds.

        If the key is already physically held (tracked in _held), emits only
        a keyDown if needed, skips the redundant keyDown call, then releases
        at the end — avoiding the duplicate transition overhead.

        Returns the actual wall-clock duration held.
        """
        if self._paused.is_set():
            return 0.0

        if jitter and self._jitter_ms > 0:
            noise = random.gauss(0, self._jitter_ms / 1000) * 0.5
            duration = max(0.01, duration + noise)

        t0 = time.perf_counter()

        if self._available:
            with self._held_lock:
                already_held = key in self._held
                self._held.add(key)
            try:
                if not already_held:
                    self._pg.keyDown(key)
                time.sleep(duration)
            finally:
                try:
                    self._pg.keyUp(key)
                except Exception:
                    pass
                with self._held_lock:
                    self._held.discard(key)
        else:
            time.sleep(duration)

        return time.perf_counter() - t0

    def tap_key(self, key: str, presses: int = 1) -> None:
        """Single or repeated key press (not held)."""
        if self._paused.is_set():
            return
        if self._available:
            self._pg.press(key, presses=presses)

    def release_all(self) -> None:
        """
        Emergency key release.  Safe to call from any thread at any time.
        Releases all tracked held keys AND all common movement keys.
        """
        if not self._available:
            return
        with self._held_lock:
            tracked = set(self._held)

        for k in (tracked | set(_ALL_MOVEMENT)):
            try:
                self._pg.keyUp(k)
            except Exception:
                pass

        with self._held_lock:
            self._held.clear()
        log.debug("InputInterface.release_all() called")

    # ------------------------------------------------------------------ #
    # Pause gate (blocks input without releasing keys)                    #
    # ------------------------------------------------------------------ #

    def set_paused(self, paused: bool) -> None:
        """When paused, press_key and tap_key become no-ops."""
        if paused:
            self.release_all()
            self._paused.set()
        else:
            self._paused.clear()

    # ------------------------------------------------------------------ #
    # Diagnostics                                                          #
    # ------------------------------------------------------------------ #

    def held_keys(self) -> frozenset[str]:
        with self._held_lock:
            return frozenset(self._held)

    @property
    def available(self) -> bool:
        return self._available


# Module-level singleton
_instance: Optional[InputInterface] = None
_inst_lock = threading.Lock()


def get_input() -> InputInterface:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = InputInterface()
    return _instance
