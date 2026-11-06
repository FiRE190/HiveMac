"""The whole Natro style loop against fakes: no screen, no keys, no sleep."""
import threading

from macro.game import FieldConfig, Game, GameSettings
from macro.loop import FarmLoop
from movement.paths import PathFile, Step


class FakeClock:
    def __init__(self):
        self.t = 0.0
    def now(self):
        return self.t
    def sleep(self, s):
        self.t += max(0.0, s)


class FakeActuator:
    def __init__(self):
        self.events = []
        self.down = set()
        self.mouse = False
    def key_down(self, k):
        self.down.add(k)
        self.events.append(("down", k))
    def key_up(self, k):
        self.down.discard(k)
        self.events.append(("up", k))
    def tap(self, k, hold_s=0.03):
        self.events.append(("tap", k))
    def mouse_down(self):
        self.mouse = True
        self.events.append(("mouse", "down"))
    def mouse_up(self):
        self.mouse = False
        self.events.append(("mouse", "up"))
    def move_mouse(self, x, y):
        self.events.append(("move", x, y))
    def release_all(self):
        self.down.clear()
        self.mouse = False
        self.events.append(("release",))
    def taps(self, key):
        return [e for e in self.events if e == ("tap", key)]


class FakeWorld:
    """A tiny model of the game: backpack fills while the tool is down in a field,
    empties while converting, resets put you at the hive, deaths can be scheduled."""

    def __init__(self, clock, act, fill_per_s=10.0, die_at=None, hive_prompt=True, hive_view=True):
        self.clock, self.act = clock, act
        self.fill = fill_per_s
        self.backpack = 0.0
        self.at_hive = False
        self.in_field = False
        self.converting_since = None
        self.die_at = die_at
        self.dead = False
        self.respawn_at = None
        self.hive_prompt = hive_prompt
        self.hive_view = hive_view
        self.resets = 0
        self.filter_resets = 0
        self.last_t = 0.0
        self.unreadable = 0

    def advance(self):
        dt = self.clock.now() - self.last_t
        self.last_t = self.clock.now()
        if self.dead and self.respawn_at is not None and self.clock.now() >= self.respawn_at:
            self.dead = False
        if self.die_at is not None and self.clock.now() >= self.die_at and not self.at_hive:
            self.dead = True
            self.respawn_at = None      # stays dead until the macro resets
            self.die_at = None
            self.in_field = False
        if self.in_field and self.act.mouse and not self.dead:
            self.backpack = min(100.0, self.backpack + self.fill * dt)
        if self.at_hive and self.converting_since is not None:
            self.backpack = max(0.0, self.backpack - 40.0 * dt)

    # the game's Esc R Enter is observed through the actuator's taps
    def observe_reset(self):
        taps = [e for e in self.act.events if e[0] == "tap"]
        n = sum(1 for e in taps if e[1] == "enter")
        if n > self.resets:
            self.resets = n
            self.dead = True
            self.respawn_at = self.clock.now() + 1.0
            self.at_hive = True
            self.in_field = False
            self.converting_since = None
            if self.die_at is None:
                pass

    # Sensors protocol
    def roblox_present(self):
        return True
    def backpack_raw(self):
        self.observe_reset()
        self.advance()
        return None if self.unreadable else int(round(self.backpack / 5.0) * 5)
    def backpack_percent(self):
        raw = self.backpack_raw()
        return 0 if raw is None else raw
    def backpack_unreadable_streak(self):
        return self.unreadable
    def reset_backpack_filter(self):
        self.filter_resets += 1
    def health_grey(self):
        self.observe_reset()
        self.advance()
        return self.dead
    def hive_prompt_visible(self):
        self.observe_reset()
        self.advance()
        if self.hive_prompt is None:
            return None
        if self.at_hive and self.converting_since is None and ("tap", "e") in self.act.events[-3:]:
            self.converting_since = self.clock.now()
        return self.at_hive
    def hive_view_visible(self):
        return self.hive_view
    def cannon_prompt_visible(self):
        return None
    def death_text_visible(self):
        return None

    def on_tap(self, key):
        if key == "e" and self.at_hive and self.converting_since is None:
            self.converting_since = self.clock.now()


def make_game(world_kwargs=None, settings=None, fields=None, stop=None):
    clock = FakeClock()
    act = FakeActuator()
    world = FakeWorld(clock, act, **(world_kwargs or {}))
    orig_tap = act.tap
    def tap(k, hold_s=0.03):
        orig_tap(k, hold_s)
        world.on_tap(k)
    act.tap = tap
    s = settings or GameSettings(walk_speed=28, hive_slot=1, reset_wait_s=1.0, death_extra_wait_s=5.0, zoom_out_taps=3)

    def lookup(kind, name, variant):
        if kind == "to_field":
            if variant == "cannon":
                return None
            return PathFile(name, [Step.gotoramp(), Step.walk("s", 9), Step.rotate("right", 2), Step.walk("d", 29)])
        return PathFile(name, [Step.walk("a", 29)])

    stop_event = stop or threading.Event()
    statuses = []
    g = Game(act, world, s, clock, stop_event=stop_event, status=lambda a, b: statuses.append((a, b)),
             window_size=lambda: (0, 0, 1600, 900), path_lookup=lookup)
    # entering the field: the travel path ends with a long right walk; we mark
    # "in field" when that walk starts by watching key downs of d after the rotate
    orig_key_down = act.key_down
    def key_down(k):
        orig_key_down(k)
        if k == "d" and any(e == ("tap", ".") for e in act.events) and world.at_hive:
            world.at_hive = False
            world.in_field = True
    act.key_down = key_down
    g.statuses = statuses
    return g, world, act, clock


def test_reset_to_hive_sends_keys_waits_for_respawn_and_fixes_camera():
    g, world, act, clock = make_game()
    assert g.reset_to_hive()
    taps = [e[1] for e in act.events if e[0] == "tap"]
    assert taps[:3] == ["esc", "r", "enter"]
    assert world.resets == 1 and world.at_hive
    assert act.taps("o") and len(act.taps("o")) == 3          # zoomed out
    assert world.filter_resets == 1
    assert clock.now() >= 1.0 + 1.0                            # respawn + reset_wait


def test_reset_retries_when_hive_prompt_missing_then_gives_up():
    g, world, act, clock = make_game(world_kwargs={"hive_prompt": False})
    world.hive_prompt = False
    # force the prompt to read False even at the hive
    world.hive_prompt_visible = lambda: False
    assert g.reset_to_hive() is False
    assert world.resets == g.settings.reset_attempts


def test_convert_presses_e_and_waits_for_empty():
    g, world, act, clock = make_game()
    world.at_hive = True
    world.backpack = 80
    assert g.convert()
    assert ("tap", "e") in act.events
    assert world.backpack == 0


def test_gather_stops_at_backpack_target_and_releases_tool():
    g, world, act, clock = make_game(world_kwargs={"fill_per_s": 20.0})
    assert g.reset_to_hive() and g.convert()
    f = FieldConfig.from_dict({"name": "sunflower", "backpack_percent": 90, "minutes": 30})
    assert g.travel_to(f)
    assert world.in_field
    res = g.gather(f)
    assert res.reason == "backpack"
    assert res.backpack >= 88
    assert not act.mouse and not act.down
    assert res.seconds < 30 * 60


def test_gather_stops_on_time_limit():
    g, world, act, clock = make_game(world_kwargs={"fill_per_s": 0.1})
    g.reset_to_hive()
    g.convert()
    f = FieldConfig.from_dict({"name": "sunflower", "backpack_percent": 95, "minutes": 0.5})
    g.travel_to(f)
    res = g.gather(f)
    assert res.reason == "time"
    assert 30 <= res.seconds < 60


def test_death_during_gather_then_loop_resets_with_extra_wait():
    g, world, act, clock = make_game(world_kwargs={"fill_per_s": 1.0, "die_at": 40.0})
    f = FieldConfig.from_dict({"name": "sunflower", "backpack_percent": 95, "minutes": 30})
    loop = FarmLoop(g, [f], max_cycles=2)
    why = loop.run()
    assert why == "cycles_done"
    assert loop.stats.deaths == 1
    assert loop.stats.history[0].reason == "death"
    # after the death the second reset waited the extra time
    assert loop.stats.cycles == 2 and loop.stats.resets >= 2
    assert not act.down and not act.mouse


def test_loop_rotates_fields_and_stop_event_ends_it():
    g, world, act, clock = make_game(world_kwargs={"fill_per_s": 50.0})
    f1 = FieldConfig.from_dict({"name": "sunflower", "backpack_percent": 90})
    f2 = FieldConfig.from_dict({"name": "dandelion", "backpack_percent": 90})
    f3 = FieldConfig.from_dict({"name": "clover", "enabled": False})
    loop = FarmLoop(g, [f1, f2, f3], max_cycles=3)
    assert [f.name for f in loop.fields] == ["sunflower", "dandelion"]
    assert loop.run() == "cycles_done"
    traveled = [d for s, d in g.statuses if s == "traveling"]
    assert traveled == ["sunflower", "dandelion", "sunflower"]
    assert loop.stats.converts == 3

    g.stop_event.set()
    assert FarmLoop(g, [f1]).run() == "stopped"


def test_loop_gives_up_after_repeated_reset_failures():
    g, world, act, clock = make_game()
    world.hive_prompt_visible = lambda: False
    f = FieldConfig.from_dict({"name": "sunflower"})
    loop = FarmLoop(g, [f], max_failed_resets=2)
    assert loop.run() == "reset_failed"
    assert loop.stats.failed_resets == 2


def test_field_config_takes_natro_defaults_and_overrides():
    f = FieldConfig.from_dict({"name": "Blue Flower"})
    assert f.camera == "right" and f.turns == 2 and f.pattern == "corner_x_snake" and f.width == 7
    f2 = FieldConfig.from_dict({"name": "blue flower", "width": 3, "travel": "cannon"})
    assert f2.width == 3 and f2.travel == "cannon"
    assert FieldConfig.from_dict(f2.to_dict()) == f2


def test_game_settings_from_config_ignores_unknown_and_casts():
    s = GameSettings.from_config({"walk_speed": "31", "hive_slot": 3.0, "nonsense": 1, "mouse_park": [0.5, 0.5]})
    assert s.walk_speed == 31.0 and s.hive_slot == 3 and s.mouse_park == (0.5, 0.5)
