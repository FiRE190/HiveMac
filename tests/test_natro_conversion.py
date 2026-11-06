"""The Natro AHK -> JSON path converter, and the walk-back routes it produced."""
import json

import pytest

from macro.game import FieldConfig
from movement.paths import PATHS_DIR, _flatten_natro, convert_natro_path

NATRO_FIELDS = [
    "bamboo", "blue_flower", "cactus", "clover", "coconut", "dandelion", "mountain_top", "mushroom",
    "pepper", "pine_tree", "pineapple", "pumpkin", "rose", "spider", "strawberry", "stump", "sunflower",
]


def tiles(steps):
    return [(s.keys, s.tiles) for s in steps if s.type == "walk"]


def test_loop_repeats_its_body():
    src = "Loop 3\n{\n\tnm_Walk(2, BackKey)\n}\nnm_Walk(1, FwdKey)"
    steps = convert_natro_path(src)["walk"]
    assert tiles(steps) == [(["s"], 2.0)] * 3 + [(["w"], 1.0)]


def test_switch_hiveslot_keeps_the_default_branch():
    src = ("nm_Walk(5, FwdKey)\nswitch HiveSlot\n{\ncase 3:\nnm_Walk(2.7, BackKey)\n\n"
           "default:\nnm_Walk(1.5, BackKey)\nnm_Walk(35, RightKey)\n}")
    assert tiles(convert_natro_path(src)["walk"]) == [(["w"], 5.0), (["s"], 1.5), (["d"], 35.0)]


def test_hivebees_condition_keeps_the_walking_branch_and_drops_else():
    src = ('if (HiveBees < 12) { ;walk\n\tnm_Walk(12, FwdKey)\n\t}\nelse {\n\tsend "{e down}"\n'
           '\tsend "{e up}"\n}\nnm_Walk(1, BackKey)')
    steps = convert_natro_path(src)["walk"]
    assert tiles(steps) == [(["w"], 12.0), (["s"], 1.0)]
    assert not any(s.type == "tap" for s in steps)


def test_compound_condition_and_braces_inside_strings():
    src = ('If ((HiveBees < 25) || (MoveMethod = "Walk")) {\n\tsend "{" RotLeft " 4}"\n\tnm_Walk(3, FwdKey)\n}\n'
           'else {\n\tnm_Walk(9, BackKey)\n}')
    steps = convert_natro_path(src)["walk"]
    assert [s.type for s in steps] == ["rotate", "walk"]
    assert steps[0].count == 4 and steps[1].tiles == 3.0


def test_unbalanced_braces_are_an_error_not_a_silent_drop():
    with pytest.raises(ValueError):
        _flatten_natro("Loop 2\n{\nnm_Walk(1, FwdKey)\n")


def test_jump_and_e_press_use_real_key_names():
    src = 'send "{" FwdKey " down}"\nsend "{" SC_Space " down}"\nHyperSleep(200)\nsend "{" SC_Space " up}"\nsend "{" FwdKey " up}"\nsend("{" SC_E " down}")\nsend("{" SC_E " up}")'
    steps = convert_natro_path(src)["walk"]
    keys = {k for s in steps for k in s.keys} | {s.key for s in steps if s.key}
    assert "sc_space" not in keys and "sc_e" not in keys
    assert any(s.type == "tap" and s.key == "e" for s in steps)
    assert any(s.type == "hold" and "space" in s.keys for s in steps)


@pytest.mark.parametrize("field", NATRO_FIELDS)
def test_every_field_has_a_walk_back_route(field):
    f = PATHS_DIR / "natro" / "to_hive" / f"{field}.json"
    assert f.exists(), f"missing walk-back route for {field}"
    data = json.loads(f.read_text())
    assert data["steps"], f"empty route for {field}"
    for s in data["steps"]:
        for k in s.get("keys", []) + ([s["key"]] if s.get("key") else []):
            assert not k.startswith("sc_"), (field, k)


def test_return_method_defaults_to_walk_like_natro():
    assert FieldConfig.from_dict({"name": "sunflower"}).return_method == "walk"
    assert FieldConfig.from_dict({"name": "sunflower", "return_method": "reset"}).return_method == "reset"


def test_hive_profile_defaults_exist():
    cfg = json.loads((PATHS_DIR.parent / "default_config.json").read_text())
    hive = cfg["hive"]
    assert hive["bee_count"] == 50 and hive["cub_buddy"] is False
    assert hive["color"] in ("blue", "red", "white", "mixed")
    assert 0 < hive["backpack_percent"] <= 100 and 1 <= hive["avg_bee_level"] <= 25
