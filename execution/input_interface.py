"""
The only module that talks to pynput. Everything else asks for keys and mouse
through here, so release_all() always knows what is held and tests can swap in
a fake.

pynput posts Quartz CGEvents on macOS, the same route the Existance macro uses
through pyautogui, and Roblox accepts them. Accessibility permission for the
terminal (or Python) is required.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from utils.logger import get_logger

log = get_logger(__name__)

MOVEMENT_KEYS = ("w", "a", "s", "d", "space", "shift")


class InputInterface:
    def __init__(self) -> None:
        self._held: set[str] = set()
        self._lock = threading.Lock()
        self._paused = threading.Event()
        self._mouse_down = False
        try:
            from pynput import keyboard, mouse
            self._kb = keyboard.Controller()
            self._mouse = mouse.Controller()
            self._Key = keyboard.Key
            self._Button = mouse.Button
            self.available = True
        except Exception as exc:  # pragma: no cover - depends on the host
            log.warning("pynput unavailable, input is simulated: %s", exc)
            self._kb = self._mouse = None
            self.available = False

    # -- key translation ---------------------------------------------------
    def _key(self, name: str):
        special = {
            "space": "space", "esc": "esc", "escape": "esc", "enter": "enter", "return": "enter",
            "shift": "shift", "pageup": "page_up", "pagedown": "page_down", "tab": "tab",
            "ctrl": "ctrl", "cmd": "cmd", "alt": "alt", "up": "up", "down": "down", "left": "left", "right": "right",
        }
        n = name.lower()
        if n in special:
            return getattr(self._Key, special[n])
        if n.startswith("f") and n[1:].isdigit():
            return getattr(self._Key, n)
        return n

    # -- keys ---------------------------------------------------------------
    def key_down(self, key: str) -> None:
        if self._paused.is_set():
            return
        with self._lock:
            self._held.add(key)
        if self.available:
            try:
                self._kb.press(self._key(key))
            except Exception as exc:
                log.debug("key_down %s failed: %s", key, exc)

    def key_up(self, key: str) -> None:
        with self._lock:
            self._held.discard(key)
        if self.available:
            try:
                self._kb.release(self._key(key))
            except Exception as exc:
                log.debug("key_up %s failed: %s", key, exc)

    def tap(self, key: str, hold_s: float = 0.03) -> None:
        if self._paused.is_set():
            return
        self.key_down(key)
        time.sleep(hold_s)
        self.key_up(key)

    # -- mouse --------------------------------------------------------------
    def mouse_down(self) -> None:
        if self._paused.is_set():
            return
        self._mouse_down = True
        if self.available:
            try:
                self._mouse.press(self._Button.left)
            except Exception as exc:
                log.debug("mouse_down failed: %s", exc)

    def mouse_up(self) -> None:
        self._mouse_down = False
        if self.available:
            try:
                self._mouse.release(self._Button.left)
            except Exception as exc:
                log.debug("mouse_up failed: %s", exc)

    def click(self) -> None:
        self.mouse_down()
        time.sleep(0.04)
        self.mouse_up()

    def move_mouse(self, x: int, y: int) -> None:
        if self.available:
            try:
                self._mouse.position = (int(x), int(y))
            except Exception as exc:
                log.debug("move_mouse failed: %s", exc)

    def mouse_position(self) -> tuple[int, int]:
        if self.available:
            try:
                x, y = self._mouse.position
                return int(x), int(y)
            except Exception:
                pass
        return (0, 0)

    # -- safety -------------------------------------------------------------
    def release_all(self) -> None:
        with self._lock:
            held = set(self._held)
            self._held.clear()
        for k in held | set(MOVEMENT_KEYS):
            if self.available:
                try:
                    self._kb.release(self._key(k))
                except Exception:
                    pass
        self.mouse_up()
        log.debug("input: everything released")

    def set_paused(self, paused: bool) -> None:
        if paused:
            self.release_all()
            self._paused.set()
        else:
            self._paused.clear()

    def held_keys(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._held)


_instance: Optional[InputInterface] = None
_inst_lock = threading.Lock()


def get_input() -> InputInterface:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = InputInterface()
    return _instance
