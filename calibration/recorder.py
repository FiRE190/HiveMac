"""
Key sequence recorder: turns timestamped key down/up events into path Steps.

The pure part (`events_to_steps`) is tested. The listener part wraps pynput and
only runs when the user records a walk from the wizard.

Rules:
  - movement keys (w a s d) held together become one `walk` step; the distance is
    hold seconds * walk speed / 4 studs, so the saved path is in tiles and
    replays correctly at any speed
  - , and . become `rotate` steps (45 degrees per tap), consecutive taps merge
  - i and o become `zoom` steps
  - space and e become `tap` steps
  - gaps between actions longer than `min_gap_s` become `wait` steps
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from movement.paths import Step
from movement.walk import STUDS_PER_TILE

MOVE = {"w", "a", "s", "d"}
ROTATE = {",": "left", ".": "right"}
ZOOM = {"i": "in", "o": "out"}
TAPS = {"space", "e", "1", "2", "3", "4", "5", "6", "7"}


@dataclass
class KeyEvent:
    t: float
    key: str
    down: bool


def events_to_steps(events: list[KeyEvent], walk_speed: float, min_gap_s: float = 0.25,
                    merge_rotations: bool = True) -> list[Step]:
    steps: list[Step] = []
    events = sorted(events, key=lambda e: e.t)
    held: dict[str, float] = {}       # move key -> time pressed
    last_action_end: Optional[float] = None

    def add_wait(now: float) -> None:
        nonlocal last_action_end
        if last_action_end is not None and now - last_action_end >= min_gap_s and not held:
            steps.append(Step.wait(round(now - last_action_end, 3)))

    def close_segment(now: float) -> None:
        """Emit a walk for the keys currently held, from the latest press to now."""
        nonlocal last_action_end
        if not held:
            return
        start = max(held.values())
        dur = now - start
        if dur > 0.01:
            tiles = dur * walk_speed / STUDS_PER_TILE
            keys = sorted(held, key="wasd".index)
            if steps and steps[-1].type == "walk" and steps[-1].keys == keys:
                steps[-1].tiles = round(steps[-1].tiles + tiles, 3)
            else:
                steps.append(Step.walk(keys, round(tiles, 3)))
        for k in held:
            held[k] = now
        last_action_end = now

    for e in events:
        k = e.key.lower()
        if k in MOVE:
            if e.down:
                if k in held:
                    continue
                if held:
                    close_segment(e.t)
                else:
                    add_wait(e.t)
                held[k] = e.t
            else:
                if k not in held:
                    continue
                close_segment(e.t)
                del held[k]
            continue
        if not e.down:
            continue
        if held:
            close_segment(e.t)
        else:
            add_wait(e.t)
        if k in ROTATE:
            d = ROTATE[k]
            if merge_rotations and steps and steps[-1].type == "rotate" and steps[-1].direction == d:
                steps[-1].count += 1
            else:
                steps.append(Step.rotate(d, 1))
        elif k in ZOOM:
            d = ZOOM[k]
            if steps and steps[-1].type == "zoom" and steps[-1].direction == d:
                steps[-1].count += 1
            else:
                steps.append(Step.zoom(d, 1))
        elif k in TAPS:
            steps.append(Step.tap(k, 1))
        else:
            continue
        last_action_end = e.t
    if held:
        close_segment(events[-1].t if events else time.perf_counter())
    return steps


class KeyRecorder:
    """Records global key events with pynput until stop() is called."""

    def __init__(self, on_event: Optional[Callable[[KeyEvent], None]] = None) -> None:
        self.events: list[KeyEvent] = []
        self._on_event = on_event
        self._listener = None
        self._lock = threading.Lock()
        self.started_at: float = 0.0

    @staticmethod
    def _name(key) -> Optional[str]:
        try:
            if key.char is not None:
                return key.char.lower()
        except AttributeError:
            pass
        name = getattr(key, "name", None)
        if name in ("space",):
            return name
        return None

    def _push(self, key, down: bool) -> None:
        name = self._name(key)
        if name is None:
            return
        ev = KeyEvent(time.perf_counter(), name, down)
        with self._lock:
            self.events.append(ev)
        if self._on_event:
            try:
                self._on_event(ev)
            except Exception:
                pass

    def start(self) -> None:
        from pynput import keyboard
        self.events = []
        self.started_at = time.perf_counter()
        self._listener = keyboard.Listener(on_press=lambda k: self._push(k, True),
                                           on_release=lambda k: self._push(k, False))
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> list[KeyEvent]:
        if self._listener:
            self._listener.stop()
            self._listener = None
        with self._lock:
            return list(self.events)
