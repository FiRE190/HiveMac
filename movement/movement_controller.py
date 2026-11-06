"""
Movement controller: translates pattern offsets and destination names
into real keyboard/mouse actions via pyautogui.

Key design:
- All movement checks state_manager.is_paused and stop_event before each step
- navigate_to() uses waypoints from config/coordinates.json
- hold_key() / click() add human-like timing automatically
"""
import json
import threading
import time
from pathlib import Path
from typing import Optional

import pyautogui

from config.config_manager import get_config
from movement.patterns import MovementPattern
from movement.randomizer import jitter, human_sleep, micro_pause
from state.state_manager import get_state
from utils.logger import get_logger

log = get_logger(__name__)

pyautogui.FAILSAFE = True  # move mouse to corner to abort
pyautogui.PAUSE = 0.0      # we manage all timing ourselves

_COORDS_FILE = Path(__file__).parent.parent / "config" / "coordinates.json"


def _load_coordinates() -> dict:
    if _COORDS_FILE.exists():
        with open(_COORDS_FILE, "r") as f:
            return json.load(f)
    return {}


class MovementController:
    _instance: "MovementController | None" = None
    _cls_lock = threading.Lock()

    def __new__(cls) -> "MovementController":
        with cls._cls_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._lock = threading.Lock()
                cls._instance = inst
        return cls._instance

    # ------------------------------------------------------------------ #

    def hold_key(
        self,
        key: str,
        duration_sec: float,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        """Hold a key for approximately duration_sec, checking for stop/pause."""
        sm = get_state()
        try:
            pyautogui.keyDown(key)
            end_time = time.time() + duration_sec
            while time.time() < end_time:
                if stop_event and stop_event.is_set():
                    break
                while sm.is_paused:
                    pyautogui.keyUp(key)
                    time.sleep(0.1)
                    pyautogui.keyDown(key)
                time.sleep(0.05)
        finally:
            pyautogui.keyUp(key)

    def tap_key(self, key: str, times: int = 1, interval_ms: float = 80) -> None:
        for _ in range(times):
            pyautogui.press(key)
            human_sleep(interval_ms, 20)

    def click(self, x: float, y: float, do_jitter: bool = True) -> None:
        if do_jitter:
            x, y = jitter(x, y, radius=4)
        pyautogui.click(int(x), int(y))
        human_sleep(80, 20)

    def move_to(self, x: float, y: float, duration: float = 0.12) -> None:
        jx, jy = jitter(x, y, radius=3)
        pyautogui.moveTo(int(jx), int(jy), duration=duration)

    def navigate_to(
        self,
        destination: str,
        stop_event: Optional[threading.Event] = None,
        timeout_sec: float = 60.0,
    ) -> bool:
        """
        Navigate to a named destination using stored waypoints.
        Returns True on successful arrival, False on timeout/stop.

        Destinations are defined in config/coordinates.json as:
        {
          "hive": {"x": 512, "y": 300},
          "sunflower_field": {"x": 800, "y": 400},
          ...
        }
        Each destination is a click/walk target. For multi-step routes,
        define "route_<destination>" as a list of coordinate names to visit.
        """
        coords = _load_coordinates()
        sm = get_state()

        # Check for a multi-step route first
        route_key = f"route_{destination.lower().replace(' ', '_')}"
        if route_key in coords:
            waypoints = coords[route_key]
            for wp_name in waypoints:
                if stop_event and stop_event.is_set():
                    return False
                wp = coords.get(wp_name)
                if wp:
                    self._walk_to_point(wp["x"], wp["y"], stop_event, timeout_sec)
            return True

        # Single destination
        dest_key = destination.lower().replace(" ", "_")
        dest = coords.get(dest_key) or coords.get(destination)
        if not dest:
            log.warning("No coordinates for destination '%s'", destination)
            return False

        return self._walk_to_point(dest["x"], dest["y"], stop_event, timeout_sec)

    def _walk_to_point(
        self,
        target_x: float,
        target_y: float,
        stop_event: Optional[threading.Event],
        timeout_sec: float,
    ) -> bool:
        """
        Simulate walking toward a screen coordinate by holding movement keys.
        This is a simplified walk — calibration defines the rough direction.
        """
        sm = get_state()
        cfg = get_config()

        # Click near target and hold W (forward) for a set duration
        self.click(target_x, target_y)
        human_sleep(150, 30)

        start = time.time()
        while time.time() - start < timeout_sec:
            if stop_event and stop_event.is_set():
                return False
            while sm.is_paused:
                time.sleep(0.1)
            # Brief forward burst with jitter
            self.hold_key("w", random_duration(0.4), stop_event)
            micro_pause(0.2)
            if time.time() - start > 3.0:
                break  # assume arrived after ~3s of movement

        return True

    def move_pattern(
        self,
        pattern: MovementPattern,
        duration_sec: float,
        origin: Optional[tuple[float, float]] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        """
        Execute a movement pattern for duration_sec seconds around origin.
        If origin is None, uses current mouse position.
        Movement is translated to WASD key presses, not raw mouse movement,
        since Roblox uses keyboard for character control.
        """
        sm = get_state()
        cfg = get_config()
        base_delay_ms = cfg.get("timing.movement_loop_delay_ms", 80)

        start = time.time()
        key_map = {
            "right": "d",
            "left": "a",
            "forward": "w",
            "backward": "s",
        }

        prev_dx, prev_dy = 0.0, 0.0
        for dx, dy in pattern.steps(max_steps=10000):
            if stop_event and stop_event.is_set():
                break
            if time.time() - start >= duration_sec:
                break

            while sm.is_paused:
                time.sleep(0.1)

            sm.heartbeat()

            # Map delta to key presses
            self._press_direction(dx - prev_dx, dy - prev_dy, stop_event)
            prev_dx, prev_dy = dx, dy

            micro_pause(
                cfg.get("movement.micro_pause_chance", 0.08),
                cfg.get("movement.micro_pause_min_ms", 50),
                cfg.get("movement.micro_pause_max_ms", 250),
            )
            human_sleep(base_delay_ms, base_delay_ms * 0.3)

    def _press_direction(
        self,
        ddx: float,
        ddy: float,
        stop_event: Optional[threading.Event],
    ) -> None:
        """Convert a delta vector into brief WASD key taps."""
        cfg = get_config()
        hold_ms = cfg.get("timing.click_hold_ms", 120)

        if abs(ddx) > abs(ddy):
            key = "d" if ddx > 0 else "a"
        else:
            key = "s" if ddy > 0 else "w"

        self.hold_key(key, hold_ms / 1000.0, stop_event)


def random_duration(base: float) -> float:
    import random
    return base * random.uniform(0.75, 1.35)


def get_movement_controller() -> MovementController:
    return MovementController()
