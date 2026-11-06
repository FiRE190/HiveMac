"""
Open loop walking, the Natro way: hold a key for `4 * tiles / speed` seconds.

One tile is 4 studs. `speed` is the player's walk speed from the in game settings
panel (Natro default 28), times an optional live multiplier for haste and similar
buffs. The multiplier is a callable so a buff detector can be plugged in later
without touching this file; version one passes a constant 1.0.

Nothing here touches the screen. Key presses go through an `Actuator`, which is
the InputInterface in production and a fake in tests.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol, Sequence

STUDS_PER_TILE = 4.0
MOVE_KEYS = ("w", "a", "s", "d")


class Actuator(Protocol):
    def key_down(self, key: str) -> None: ...
    def key_up(self, key: str) -> None: ...
    def tap(self, key: str, hold_s: float = 0.03) -> None: ...
    def mouse_down(self) -> None: ...
    def mouse_up(self) -> None: ...
    def release_all(self) -> None: ...


class Clock(Protocol):
    def now(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class RealClock:
    def now(self) -> float:
        return time.perf_counter()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


@dataclass
class SpeedModel:
    """Walk speed in studs per second: base from settings times a live multiplier."""

    base_speed: float = 28.0
    multiplier: Callable[[], float] = field(default=lambda: 1.0)

    def current(self) -> float:
        m = self.multiplier()
        if not m or m <= 0:
            m = 1.0
        return max(1.0, self.base_speed) * m

    def seconds_for_tiles(self, tiles: float) -> float:
        return max(0.0, tiles) * STUDS_PER_TILE / self.current()


def key_duration_at_speed(seconds_at_reference: float, reference_speed: float, actual_speed: float) -> float:
    """Scale a hold recorded at one walk speed to another (Existance's t * 28 / movespeed)."""
    if actual_speed <= 0:
        return seconds_at_reference
    return seconds_at_reference * reference_speed / actual_speed


class Walker:
    """Holds movement keys for a distance in tiles, in small slices so a stop
    or pause can interrupt within `slice_s` seconds. Keys are always released.
    """

    def __init__(self, actuator: Actuator, speed: SpeedModel, clock: Clock | None = None,
                 stop_event: threading.Event | None = None,
                 pause_event: threading.Event | None = None, slice_s: float = 0.05) -> None:
        self._act = actuator
        self.speed = speed
        self._clock = clock or RealClock()
        self._stop = stop_event or threading.Event()
        self._pause = pause_event
        self._slice = slice_s

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def hold(self, keys: Sequence[str] | str, seconds: float) -> float:
        """Hold one or more keys for `seconds` of effective (unpaused) time.
        Returns how long keys were actually held. Returns early when stopped.
        """
        keys = [keys] if isinstance(keys, str) else list(keys)
        held = 0.0
        if self._stop.is_set():
            return held
        for k in keys:
            self._act.key_down(k)
        try:
            remaining = seconds
            while remaining > 0 and not self._stop.is_set():
                if self._pause is not None and self._pause.is_set():
                    for k in keys:
                        self._act.key_up(k)
                    while self._pause.is_set() and not self._stop.is_set():
                        self._clock.sleep(self._slice)
                    if self._stop.is_set():
                        return held
                    for k in keys:
                        self._act.key_down(k)
                step = min(self._slice, remaining)
                t0 = self._clock.now()
                self._clock.sleep(step)
                dt = self._clock.now() - t0
                dt = step if dt <= 0 else dt
                held += dt
                remaining -= dt
        finally:
            for k in keys:
                self._act.key_up(k)
        return held

    def walk(self, keys: Sequence[str] | str, tiles: float) -> float:
        """Natro's nm_Walk: hold keys for `tiles` tiles at the current speed."""
        return self.hold(keys, self.speed.seconds_for_tiles(tiles))

    def wait(self, seconds: float) -> None:
        """Interruptible sleep."""
        end = self._clock.now() + seconds
        while not self._stop.is_set():
            left = end - self._clock.now()
            if left <= 0:
                return
            self._clock.sleep(min(self._slice, left))

    def rotate(self, direction: str, taps: int, rot_left_key: str = ",", rot_right_key: str = ".",
               gap_s: float = 0.06) -> None:
        """Camera yaw: one tap of , or . is 45 degrees in Roblox."""
        key = rot_left_key if direction == "left" else rot_right_key
        for _ in range(int(taps)):
            if self._stop.is_set():
                return
            self._act.tap(key)
            self._clock.sleep(gap_s)

    def taps(self, key: str, count: int, gap_s: float = 0.06) -> None:
        for _ in range(int(count)):
            if self._stop.is_set():
                return
            self._act.tap(key)
            self._clock.sleep(gap_s)

    def run_steps(self, steps: Iterable, keymap: dict[str, str] | None = None) -> bool:
        """Execute a sequence of path or pattern Steps (see movement.paths).
        Returns False if interrupted by stop."""
        from movement.paths import Step  # local import to keep the module graph simple

        km = keymap or {}
        for s in steps:
            if self._stop.is_set():
                return False
            if not isinstance(s, Step):
                raise TypeError(f"not a Step: {s!r}")
            if s.type == "walk":
                self.walk([km.get(k, k) for k in s.keys], s.tiles)
            elif s.type == "hold":
                self.hold([km.get(k, k) for k in s.keys], s.seconds)
            elif s.type == "rotate":
                self.rotate(s.direction, s.count, km.get("rot_left", ","), km.get("rot_right", "."))
            elif s.type == "tap":
                self.taps(km.get(s.key, s.key), s.count)
            elif s.type == "wait":
                self.wait(s.seconds)
            elif s.type == "zoom":
                self.taps(km.get("zoom_out", "o") if s.direction == "out" else km.get("zoom_in", "i"), s.count)
            elif s.type == "mouse":
                if s.direction == "down":
                    self._act.mouse_down()
                else:
                    self._act.mouse_up()
            else:
                raise ValueError(f"unknown step type {s.type}")
        return not self._stop.is_set()
