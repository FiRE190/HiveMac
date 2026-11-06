"""Field name <-> nav node mapping and nav map integrity."""
import json
from pathlib import Path

from navigation import node_names

ROOT = Path(__file__).resolve().parent.parent


def test_display_names_round_trip_to_nodes():
    for node in node_names.field_nodes():
        assert node_names.field_to_node(node_names.node_to_display(node)) == node


def test_aliases_and_passthrough():
    assert node_names.field_to_node("Sunflower Field") == "sunflower_field"
    assert node_names.field_to_node("sunflower_field") == "sunflower_field"
    assert node_names.field_to_node("Hive") == "hive_1_entrance"
    assert node_names.field_to_node("") == ""
    assert not node_names.is_known_node("Pepper Patch")


def test_landmarks_map_to_their_node():
    assert node_names.landmark_to_node("hive_exterior") == "hive_1_entrance"
    assert node_names.landmark_to_node("spawn_platform") == "spawn_platform"
    assert node_names.landmark_to_node("no_such_landmark") is None


def test_nav_map_edges_reference_existing_nodes_and_hive_is_connected():
    data = json.loads((ROOT / "config" / "nav_map.json").read_text())
    nodes = set(data["nodes"])
    for e in data["edges"]:
        assert e["from"] in nodes, e
        assert e["to"] in nodes, e
    out_of_hive = {e["to"] for e in data["edges"] if e["from"] == "hive_1_entrance"}
    assert "spawn_platform" in out_of_hive          # hive -> spawn -> any field
    assert "wealth_clock" in nodes


def test_waypoint_pattern_without_waypoints_does_not_crash():
    from movement.patterns import PatternFactory, CircularPattern
    assert isinstance(PatternFactory.create("waypoint", radius=50), CircularPattern)
