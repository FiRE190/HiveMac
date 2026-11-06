import threading

from movement import patterns
from movement.paths import Step, bind_pattern_keys
from movement.walk import SpeedModel, Walker, key_duration_at_speed


class FakeClock:
    def __init__(self):
        self.t = 0.0
    def now(self):
        return self.t
    def sleep(self, s):
        self.t += s


class FakeActuator:
    def __init__(self):
        self.events = []
        self.down = set()
    def key_down(self, k):
        self.down.add(k)
        self.events.append(("down", k))
    def key_up(self, k):
        self.down.discard(k)
        self.events.append(("up", k))
    def tap(self, k, hold_s=0.03):
        self.events.append(("tap", k))
    def mouse_down(self):
        self.events.append(("mouse", "down"))
    def mouse_up(self):
        self.events.append(("mouse", "up"))
    def release_all(self):
        self.down.clear()


def test_speed_model_tiles_to_seconds():
    m = SpeedModel(base_speed=28.0)
    assert abs(m.seconds_for_tiles(9) - 36 / 28) < 1e-9
    m2 = SpeedModel(base_speed=28.0, multiplier=lambda: 2.0)
    assert abs(m2.seconds_for_tiles(9) - 18 / 28) < 1e-9
    assert abs(key_duration_at_speed(1.0, 28, 56) - 0.5) < 1e-9


def test_walker_holds_for_the_right_time_and_releases():
    act, clock = FakeActuator(), FakeClock()
    w = Walker(act, SpeedModel(28.0), clock=clock)
    held = w.walk(["w", "d"], 7)
    assert abs(held - 1.0) < 0.06
    assert act.events[0] == ("down", "w") and act.events[1] == ("down", "d")
    assert act.events[-2:] == [("up", "w"), ("up", "d")]
    assert not act.down


def test_walker_stops_early_and_still_releases_keys():
    act, clock = FakeActuator(), FakeClock()
    stop = threading.Event()
    w = Walker(act, SpeedModel(28.0), clock=clock, stop_event=stop, slice_s=0.1)
    orig_sleep = clock.sleep
    def sleep_then_stop(s):
        orig_sleep(s)
        if clock.t >= 0.3:
            stop.set()
    clock.sleep = sleep_then_stop
    held = w.walk("w", 70)   # would take 10 s
    assert held < 0.5
    assert not act.down
    assert w.run_steps([Step.walk("w", 1)]) is False


def test_walker_pause_releases_and_resumes():
    act, clock = FakeActuator(), FakeClock()
    pause = threading.Event()
    pause.set()
    w = Walker(act, SpeedModel(28.0), clock=clock, pause_event=pause, slice_s=0.1)
    calls = {"n": 0}
    orig_sleep = clock.sleep
    def sleep_unpause(s):
        orig_sleep(s)
        calls["n"] += 1
        if calls["n"] >= 3:
            pause.clear()
    clock.sleep = sleep_unpause
    w.hold("w", 0.2)
    # while paused the key was up; after unpause it went down again and finished
    assert ("up", "w") in act.events[:-1]
    assert act.events.count(("down", "w")) == 2
    assert not act.down


def test_run_steps_maps_abstract_keys_and_handles_every_type():
    act, clock = FakeActuator(), FakeClock()
    w = Walker(act, SpeedModel(28.0), clock=clock)
    steps = [Step.walk("tc_lr", 1), Step.rotate("right", 2), Step.tap("e"), Step.wait(0.1),
             Step.zoom("out", 3), Step.mouse("down"), Step.hold(["w"], 0.1), Step.mouse("up")]
    ok = w.run_steps(steps, bind_pattern_keys(invert_lr=True))
    assert ok
    assert ("down", "d") in act.events
    assert act.events.count(("tap", ".")) == 2
    assert act.events.count(("tap", "o")) == 3
    assert ("tap", "e") in act.events and ("mouse", "down") in act.events


def test_bind_pattern_keys():
    assert bind_pattern_keys() == {"tc_fb": "w", "afc_fb": "s", "tc_lr": "a", "afc_lr": "d"}
    assert bind_pattern_keys(invert_fb=True, invert_lr=True) == {"tc_fb": "s", "afc_fb": "w", "tc_lr": "d", "afc_lr": "a"}


def test_every_pattern_builds_finite_steps_with_abstract_keys():
    for name in patterns.PATTERNS:
        for size in ("xs", "s", "m", "l", "xl"):
            steps = patterns.build_pattern(name, size, width=3, facing_corner=1)
            assert steps, name
            for s in steps:
                assert s.type in ("walk", "wait")
                if s.type == "walk":
                    assert s.tiles > 0, (name, s)
                    assert all(k in patterns.ABSTRACT_KEYS or k == "w" for k in s.keys), (name, s)


def test_corner_x_snake_matches_natro_shape():
    steps = patterns.build_pattern("corner_x_snake", "m", width=4)
    walks = [s for s in steps if s.type == "walk"]
    assert len(walks) == 24
    # first move is toward centre on the left/right axis, 4 tiles at size M
    assert walks[0].keys == ["tc_lr"] and walks[0].tiles == 4.0
    # the corner push uses width
    assert any(s.keys == ["afc_lr"] and s.tiles == 10.0 for s in walks)


def test_field_defaults_cover_all_fields_with_known_patterns():
    for field, d in patterns.FIELD_DEFAULTS.items():
        assert d["pattern"] in patterns.PATTERNS, field
        assert d["size"] in patterns.SIZE_FACTORS
        assert d["camera"] in ("none", "left", "right")
