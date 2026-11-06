import json
from pathlib import Path

from calibration.layout import RelPoint, RelRegion, WindowBounds, natro_defaults
from calibration.recorder import KeyEvent, events_to_steps
from movement import paths
from movement.paths import PathFile, Step

ROOT = Path(__file__).resolve().parent.parent


def test_step_round_trip_json():
    steps = [Step.walk(["w", "d"], 6.75), Step.rotate("right", 2), Step.tap("e"), Step.wait(0.5),
             Step.hold("a", 1.85), Step.zoom("out", 5), Step.gotoramp()]
    pf = PathFile("x", steps, source="test")
    back = PathFile.from_dict(json.loads(json.dumps(pf.to_dict())))
    assert back.steps == steps
    assert back.walk_speed == 28.0


def test_gotoramp_expands_by_hive_slot():
    out = paths.expand_path([Step.gotoramp(), Step.walk("s", 1)], hive_slot=6)
    assert out[0] == Step.walk("w", 5)
    assert abs(out[1].tiles - (9.2 * 6 - 4)) < 1e-9
    assert out[2] == Step.walk("s", 1)
    assert paths.expand_path([Step.gotoramp()], hive_slot=99)[1].tiles == paths.gotoramp_steps(6)[1].tiles


def test_scale_holds_only_touches_movement_holds():
    steps = [Step.hold("w", 1.0), Step.hold("space", 0.2), Step.wait(1.0)]
    out = paths.scale_holds(steps, recorded_speed=28, actual_speed=56)
    assert abs(out[0].seconds - 0.5) < 1e-9
    assert out[1].seconds == 0.2 and out[2].seconds == 1.0


def test_convert_natro_walk_path():
    text = ('﻿nm_gotoramp()\nnm_Walk(9, BackKey)\nnm_Walk(6.75, BackKey, RightKey)\n'
            'send "{" RotRight " 2}"\nnm_Walk(29, RightKey)\n;path 230212 zaappiix\n')
    b = paths.convert_natro_path(text)
    assert list(b) == ["walk"]
    assert b["walk"] == [Step.gotoramp(), Step.walk("s", 9), Step.walk(["s", "d"], 6.75),
                         Step.rotate("right", 2), Step.walk("d", 29)]


def test_convert_natro_cannon_branch():
    text = '''if (MoveMethod = "Cannon") {
    nm_gotoramp()
    nm_gotocannon()
    send "{e down}"
    HyperSleep(100)
    send "{e up}{" LeftKey " down}"
    HyperSleep(1850)
    send "{space 2}"
    HyperSleep(2750)
    send "{" LeftKey " up}{" BackKey " down}"
    HyperSleep(1150)
    send "{" BackKey " up}{space}{" RotRight " 4}"
    Sleep 2000
} else {
    nm_gotoramp()
	nm_Walk(67.5, BackKey, LeftKey)
	send "{" RotRight " 4}"
}
'''
    b = paths.convert_natro_path(text)
    assert set(b) == {"walk", "cannon"}
    c = b["cannon"]
    assert c[0] == Step.gotoramp() and c[1].type == "gotocannon"
    assert Step.tap("e") in c
    assert Step.hold(["a"], 1.85) in c
    assert Step.tap("space", 2) in c
    assert Step.hold(["a", "s"], 2.75) in c or Step.hold(["s"], 1.15) in c
    assert c[-2] == Step.rotate("right", 4) and c[-1] == Step.wait(2.0)
    assert b["walk"] == [Step.gotoramp(), Step.walk(["s", "a"], 67.5), Step.rotate("right", 4)]


def test_convert_rejects_unknown_lines():
    try:
        paths.convert_natro_path("MsgBox hello")
    except ValueError as e:
        assert "cannot convert" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_shipped_natro_paths_load_and_cover_every_field():
    fields = paths.list_fields_with_paths("to_field")
    assert len(fields) == 17, fields
    for f in fields:
        p = paths.find_path_file("to_field", f.replace("_", " "))
        assert p is not None, f
        pf = PathFile.load(p)
        assert pf.steps[0] == Step.gotoramp(), f
        steps = list(paths.iter_steps(pf, hive_slot=1, actual_speed=28))
        assert all(s.type != "gotoramp" for s in steps)
        assert paths.total_seconds(steps, 28) > 1
    assert paths.find_path_file("to_field", "pineapple", "cannon") is not None
    assert paths.find_path_file("to_hive", "sunflower") is not None
    assert paths.find_path_file("to_field", "no such field") is None


def test_relative_points_and_regions_round_trip():
    w = WindowBounds(100, 50, 1600, 900)
    p = RelPoint.from_absolute(900, 56, w)
    assert p.absolute(w) == (900, 56)
    r = RelRegion.from_absolute({"left": 700, "top": 50, "width": 400, "height": 125}, w)
    assert r.absolute(w) == {"left": 700, "top": 50, "width": 400, "height": 125}
    moved = WindowBounds(0, 0, 1600, 900)
    assert p.absolute(moved) == (800, 6)
    d = natro_defaults(w, offset_y=20)
    assert RelPoint.from_dict(d["backpack_pixel"]).absolute(w) == (100 + 862, 50 + 26)
    assert RelPoint.from_dict(d["health_pixel"]).absolute(w) == (100 + 1525, 50 + 36)


def test_recorder_events_become_steps_in_tiles():
    ev = [KeyEvent(0.0, "w", True), KeyEvent(1.0, "w", False),          # 1 s forward = 7 tiles at 28
          KeyEvent(1.1, "d", True), KeyEvent(1.6, "w", True),           # d alone 0.5 s, then w+d 0.5 s
          KeyEvent(2.1, "w", False), KeyEvent(2.1, "d", False),
          KeyEvent(2.2, ".", True), KeyEvent(2.25, ".", False), KeyEvent(2.3, ".", True), KeyEvent(2.35, ".", False),
          KeyEvent(3.0, "e", True), KeyEvent(3.05, "e", False),
          KeyEvent(3.1, "o", True), KeyEvent(3.15, "o", False)]
    steps = events_to_steps(ev, walk_speed=28, min_gap_s=0.25)
    assert steps[0] == Step.walk(["w"], 7.0)
    assert steps[1] == Step.walk(["d"], 3.5)
    assert steps[2] == Step.walk(["w", "d"], 3.5)
    assert steps[3] == Step.rotate("right", 2)
    assert steps[4].type == "wait" and abs(steps[4].seconds - 0.7) < 1e-6
    assert steps[5] == Step.tap("e") and steps[6] == Step.zoom("out", 1)


def test_recorder_ignores_unknown_keys_and_handles_unterminated_hold():
    ev = [KeyEvent(0.0, "x", True), KeyEvent(0.5, "w", True)]
    steps = events_to_steps(ev, walk_speed=28)
    assert steps == []
    ev.append(KeyEvent(1.5, "e", True))
    steps = events_to_steps(ev, walk_speed=28)
    assert steps[0] == Step.walk(["w"], 7.0) and steps[1] == Step.tap("e")
