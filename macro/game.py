"""
The Natro style game actions, written against two small protocols so the whole
loop can run in tests with fakes:

  Sensors   what the macro can see (backpack pixel, health pixel, hive prompt...)
  Actuator  keys and mouse (execution.input_interface in production)

Every action is interruptible through the Walker's stop and pause events and
leaves no key held when it returns.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

from movement import sprinkler
from movement.paths import PathFile, Step, bind_pattern_keys, find_path_file, iter_steps
from movement.patterns import FIELD_DEFAULTS, build_pattern
from movement.walk import Actuator, Clock, SpeedModel, Walker


class Sensors(Protocol):
    def roblox_present(self) -> bool: ...
    def backpack_raw(self) -> Optional[int]: ...
    def backpack_percent(self) -> int: ...
    def backpack_unreadable_streak(self) -> int: ...
    def reset_backpack_filter(self) -> None: ...
    def health_grey(self) -> bool: ...
    def hive_prompt_visible(self) -> Optional[bool]: ...
    def hive_view_visible(self) -> Optional[bool]: ...
    def cannon_prompt_visible(self) -> Optional[bool]: ...
    def death_text_visible(self) -> Optional[bool]: ...


@dataclass
class GameSettings:
    walk_speed: float = 28.0
    hive_slot: int = 1
    sprinkler_type: str = "none"
    sprinkler_slot_key: str = "1"
    travel: str = "walk"              # default path variant: walk or cannon
    zoom_out_taps: int = 6
    reset_wait_s: float = 2.0         # minimum time between reset and the next walk
    death_extra_wait_s: float = 18.0  # the death screen is longer than a plain reset
    reset_attempts: int = 5
    respawn_timeout_s: float = 12.0
    convert_timeout_s: float = 300.0
    convert_press_retry_s: float = 6.0
    camera_search_taps: int = 2       # yaw step while looking for the hive view
    camera_after_found_taps: int = 4  # Natro: 180 degrees once the hive is in view
    use_tool: bool = True             # hold the mouse button while gathering
    check_interval_s: float = 0.25    # death and backpack sampling while walking
    backpack_sample_s: float = 1.0
    lost_screen_s: float = 60.0       # unreadable backpack this long means we are lost
    key_gap_s: float = 0.3            # between Esc, R, Enter
    rot_left: str = ","
    rot_right: str = "."
    zoom_in: str = "i"
    zoom_out: str = "o"
    mouse_park: tuple[float, float] = (0.25, 0.2)   # fraction of the window

    @staticmethod
    def from_config(cfg: dict) -> "GameSettings":
        s = GameSettings()
        for k, v in cfg.items():
            if hasattr(s, k) and k != "mouse_park":
                try:
                    setattr(s, k, type(getattr(s, k))(v))
                except (TypeError, ValueError):
                    pass
        mp = cfg.get("mouse_park")
        if isinstance(mp, (list, tuple)) and len(mp) == 2:
            s.mouse_park = (float(mp[0]), float(mp[1]))
        return s


@dataclass
class FieldConfig:
    name: str
    pattern: str = "corner_x_snake"
    size: str = "m"
    width: int = 4
    invert_fb: bool = False
    invert_lr: bool = False
    camera: str = "none"          # none, left, right
    turns: int = 1
    minutes: float = 10.0
    backpack_percent: int = 95
    sprinkler_location: str = "center"
    sprinkler_distance: int = 1
    shift_lock: bool = False
    travel: str = "default"       # default, walk, cannon
    return_method: str = "reset"  # reset, walk
    enabled: bool = True

    @staticmethod
    def from_dict(d: dict) -> "FieldConfig":
        name = str(d.get("name", "sunflower")).lower()
        base = dict(FIELD_DEFAULTS.get(name, {}))
        f = FieldConfig(name=name)
        f.pattern = str(d.get("pattern", base.get("pattern", f.pattern)))
        f.size = str(d.get("size", base.get("size", f.size)))
        f.width = int(d.get("width", base.get("width", f.width)))
        f.invert_fb = bool(d.get("invert_fb", base.get("invert_fb", False)))
        f.invert_lr = bool(d.get("invert_lr", base.get("invert_lr", False)))
        f.camera = str(d.get("camera", base.get("camera", "none")))
        f.turns = int(d.get("turns", base.get("turns", 1)))
        f.minutes = float(d.get("minutes", 10.0))
        f.backpack_percent = int(d.get("backpack_percent", 95))
        f.sprinkler_location = str(d.get("sprinkler_location", base.get("sprinkler", "center")))
        f.sprinkler_distance = int(d.get("sprinkler_distance", base.get("distance", 1)))
        f.shift_lock = bool(d.get("shift_lock", False))
        f.travel = str(d.get("travel", "default"))
        f.return_method = str(d.get("return_method", "reset"))
        f.enabled = bool(d.get("enabled", True))
        return f

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class GatherResult:
    reason: str            # backpack, time, death, lost, stopped
    seconds: float = 0.0
    backpack: int = 0


@dataclass
class Game:
    actuator: Actuator
    sensors: Sensors
    settings: GameSettings
    clock: Clock
    stop_event: threading.Event = field(default_factory=threading.Event)
    pause_event: threading.Event = field(default_factory=threading.Event)
    status: Callable[[str, str], None] = field(default=lambda state, detail: None)
    window_size: Callable[[], Optional[tuple[int, int, int, int]]] = field(default=lambda: None)
    speed_multiplier: Callable[[], float] = field(default=lambda: 1.0)
    path_lookup: Callable[[str, str, str], Optional[PathFile]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.speed = SpeedModel(self.settings.walk_speed, self.speed_multiplier)
        self.walker = Walker(self.actuator, self.speed, clock=self.clock,
                             stop_event=self.stop_event, pause_event=self.pause_event)
        self.shift_locked = False
        self.died = False
        self.last_reset_at: float = -1e9
        if self.path_lookup is None:
            self.path_lookup = self._default_path_lookup

    @staticmethod
    def _default_path_lookup(kind: str, field_name: str, variant: str) -> Optional[PathFile]:
        p = find_path_file(kind, field_name, variant)
        return PathFile.load(p) if p else None

    # -- small helpers ------------------------------------------------------
    @property
    def stopped(self) -> bool:
        return self.stop_event.is_set()

    def _wait(self, seconds: float) -> None:
        self.walker.wait(seconds)

    def _tap(self, key: str) -> None:
        self.actuator.tap(key)

    def keymap(self) -> dict[str, str]:
        return {"rot_left": self.settings.rot_left, "rot_right": self.settings.rot_right,
                "zoom_in": self.settings.zoom_in, "zoom_out": self.settings.zoom_out}

    def park_mouse(self) -> None:
        ws = self.window_size()
        mover = getattr(self.actuator, "move_mouse", None)
        if ws and mover:
            left, top, width, height = ws
            fx, fy = self.settings.mouse_park
            mover(left + int(width * fx), top + int(height * fy))

    def set_shift_lock(self, on: bool) -> None:
        if on != self.shift_locked:
            self._tap("shift")
            self.shift_locked = on
            self._wait(0.2)

    def release_everything(self) -> None:
        self.actuator.release_all()

    # -- reset ----------------------------------------------------------------
    def reset_to_hive(self, after_death: bool = False) -> bool:
        """Esc, R, Enter; wait for the respawn; confirm the hive; fix the camera."""
        s = self.settings
        self.release_everything()
        self.set_shift_lock(False)
        for attempt in range(1, s.reset_attempts + 1):
            if self.stopped:
                return False
            self.status("resetting", f"attempt {attempt}")
            self.park_mouse()
            self._tap("esc")
            self._wait(s.key_gap_s)
            self._tap("r")
            self._wait(s.key_gap_s)
            self._tap("enter")
            self.last_reset_at = self.clock.now()
            self._wait_for_respawn()
            extra = s.death_extra_wait_s if (after_death or self.died) else 0.0
            self.died = False
            self._wait(s.reset_wait_s + extra)
            if self.stopped:
                return False
            self.sensors.reset_backpack_filter()
            at_hive = self.sensors.hive_prompt_visible()
            if at_hive is False:
                self.status("resetting", "hive prompt not seen, retrying")
                continue
            if at_hive is None:
                self.status("resetting", "no hive prompt template, assuming at hive")
            self.fix_camera()
            return True
        self.status("error", "could not confirm the hive after reset")
        return False

    def _wait_for_respawn(self) -> None:
        """Natro: the health bar goes grey (dead) then comes back. Fall back to a fixed wait."""
        s = self.settings
        t0 = self.clock.now()
        seen_grey = False
        while not self.stopped and self.clock.now() - t0 < s.respawn_timeout_s:
            grey = self.sensors.health_grey()
            if grey:
                seen_grey = True
            elif seen_grey:
                return
            self._wait(0.1)
        if not seen_grey:
            # No health pixel calibrated or it never changed: give the game a moment.
            self._wait(1.0)

    def fix_camera(self) -> bool:
        """Rotate until the hive is in view (when a check exists), face away, zoom out."""
        s = self.settings
        found = self.sensors.hive_view_visible()
        if found is not None:
            taps = 0
            while found is False and taps < 16 and not self.stopped:
                self.walker.rotate("right", s.camera_search_taps, s.rot_left, s.rot_right)
                taps += s.camera_search_taps
                self._wait(0.25)
                found = self.sensors.hive_view_visible()
            if found:
                self.walker.rotate("right", s.camera_after_found_taps, s.rot_left, s.rot_right)
            else:
                self.status("warning", "hive view not found while rotating")
        self.walker.taps(s.zoom_out, s.zoom_out_taps)
        return bool(found) if found is not None else True

    # -- convert ---------------------------------------------------------------
    def convert(self) -> bool:
        """Press E at the hive and wait until the backpack reads empty."""
        s = self.settings
        if self.stopped:
            return False
        self.status("converting", "")
        t0 = self.clock.now()
        last_press = -1e9
        empty_reads = 0
        last_pct = None
        while not self.stopped and self.clock.now() - t0 < s.convert_timeout_s:
            pct = self.sensors.backpack_percent()
            if last_pct is None or (self.clock.now() - last_press > s.convert_press_retry_s and pct >= last_pct and pct > 0):
                self._tap("e")
                last_press = self.clock.now()
                last_pct = pct
            if pct <= 0:
                empty_reads += 1
                if empty_reads >= 3:
                    self.status("converting", "done")
                    return True
            else:
                empty_reads = 0
                last_pct = min(last_pct, pct) if last_pct is not None else pct
            self._wait(s.backpack_sample_s)
        return False

    # -- travel ------------------------------------------------------------------
    def travel_to(self, fcfg: FieldConfig) -> bool:
        s = self.settings
        variant = s.travel if fcfg.travel == "default" else fcfg.travel
        pf = self.path_lookup("to_field", fcfg.name, variant)
        if pf is None and variant != "walk":
            self.status("traveling", f"no {variant} path for {fcfg.name}, walking")
            pf = self.path_lookup("to_field", fcfg.name, "walk")
        if pf is None:
            self.status("error", f"no path to {fcfg.name}")
            return False
        self.status("traveling", fcfg.name)
        self.set_shift_lock(False)
        self.park_mouse()
        for step in iter_steps(pf, s.hive_slot, self.speed.current()):
            if self.stopped:
                return False
            if step.type == "gotocannon":
                if not self.go_to_cannon():
                    return False
                continue
            self.walker.run_steps([step], self.keymap())
        # start location and sprinklers
        self.walker.run_steps(sprinkler.start_location_steps(fcfg.name, fcfg.sprinkler_location,
                                                             fcfg.sprinkler_distance, self.speed.current()))
        self.walker.run_steps(sprinkler.placement_steps(s.sprinkler_type, fcfg.sprinkler_location,
                                                        s.sprinkler_slot_key, self.speed.current()))
        if fcfg.camera in ("left", "right") and fcfg.turns > 0:
            self.walker.rotate(fcfg.camera, fcfg.turns, s.rot_left, s.rot_right)
        return not self.stopped

    def go_to_cannon(self) -> bool:
        """Natro nm_gotoCannon, simplified: jump right onto the pad, then creep right
        until the cannon prompt shows (when a template exists)."""
        s = self.settings
        for _ in range(3):
            if self.stopped:
                return False
            self.actuator.key_down("space")
            self.actuator.key_down("d")
            self._wait(0.1)
            self.actuator.key_up("space")
            self.walker.walk("d", 2)
            self.walker.walk(["w", "d"], 1.5)
            self.actuator.key_up("d")
            seen = self.sensors.cannon_prompt_visible()
            if seen is None:
                return True
            t0 = self.clock.now()
            self.actuator.key_down("d")
            while not seen and self.clock.now() - t0 < 2.0 and not self.stopped:
                self._wait(0.1)
                seen = self.sensors.cannon_prompt_visible()
            self.actuator.key_up("d")
            if seen:
                return True
            self.status("traveling", "cannon not found, resetting")
            if not self.reset_to_hive():
                return False
            self.walker.run_steps(iter_steps(PathFile("ramp", [Step.gotoramp()]), s.hive_slot, self.speed.current()))
        return False

    # -- gather --------------------------------------------------------------------
    def gather(self, fcfg: FieldConfig) -> GatherResult:
        s = self.settings
        keymap = dict(self.keymap())
        keymap.update(bind_pattern_keys(fcfg.invert_fb, fcfg.invert_lr))
        steps = build_pattern(fcfg.pattern, fcfg.size, fcfg.width)
        self.status("gathering", f"{fcfg.name} {fcfg.pattern} {fcfg.size} w{fcfg.width} until {fcfg.backpack_percent}% or {fcfg.minutes:g} min")
        t0 = self.clock.now()
        last_sample = -1e9
        grey_streak = 0
        reason = "stopped"
        pct = self.sensors.backpack_percent()
        self.set_shift_lock(fcfg.shift_lock)
        self.park_mouse()
        if s.use_tool:
            self.actuator.mouse_down()
        try:
            while not self.stopped:
                for step in steps:
                    if self.stopped:
                        break
                    now = self.clock.now()
                    if now - last_sample >= s.backpack_sample_s:
                        last_sample = now
                        pct = self.sensors.backpack_percent()
                        grey_streak = grey_streak + 1 if self.sensors.health_grey() else 0
                        dead_text = self.sensors.death_text_visible()
                        if grey_streak >= 2 or dead_text:
                            self.died = True
                            reason = "death"
                            break
                        if pct >= fcfg.backpack_percent:
                            reason = "backpack"
                            break
                        if self.sensors.backpack_unreadable_streak() * s.backpack_sample_s >= s.lost_screen_s:
                            reason = "lost"
                            break
                    if now - t0 >= fcfg.minutes * 60.0:
                        reason = "time"
                        break
                    self.walker.run_steps([step], keymap)
                else:
                    continue
                break
        finally:
            if s.use_tool:
                self.actuator.mouse_up()
            self.set_shift_lock(False)
        if self.stopped:
            reason = "stopped"
        return GatherResult(reason, self.clock.now() - t0, pct)

    # -- walk back (optional) ------------------------------------------------------
    def walk_back(self, fcfg: FieldConfig) -> bool:
        s = self.settings
        pf = self.path_lookup("to_hive", fcfg.name, "walk")
        if pf is None:
            return False
        self.status("traveling", "hive")
        if fcfg.camera in ("left", "right") and fcfg.turns > 0:
            self.walker.rotate("right" if fcfg.camera == "left" else "left", fcfg.turns, s.rot_left, s.rot_right)
        self.set_shift_lock(False)
        for step in iter_steps(pf, s.hive_slot, self.speed.current()):
            if self.stopped:
                return False
            self.walker.run_steps([step], self.keymap())
        # Natro nm_findHiveSlot: slide left until the hive prompt shows
        t0 = self.clock.now()
        seen = self.sensors.hive_prompt_visible()
        if seen is None:
            return True
        self.actuator.key_down("a")
        try:
            while not seen and self.clock.now() - t0 < 15 and not self.stopped:
                self._wait(0.1)
                seen = self.sensors.hive_prompt_visible()
        finally:
            self.actuator.key_up("a")
        return bool(seen)
