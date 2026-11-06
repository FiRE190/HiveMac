"""
One place that maps what the user sees ("Sunflower Field") to what the nav map uses
("sunflower_field"), and back. The UI, profiles and tasks all go through here, so a
profile saved with a display name still resolves to a nav node.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_NAV_MAP = Path(__file__).resolve().parent.parent / "config" / "nav_map.json"

# Display names that do not follow the plain lower-case rule.
_ALIASES = {
    "pine tree forest": "pine_tree_forest",
    "pine forest": "pine_tree_forest",
    "hive": "hive_1_entrance",
    "hive 1": "hive_1_entrance",
    "spawn": "spawn_platform",
}


@lru_cache(maxsize=1)
def nav_nodes() -> dict[str, dict]:
    """node id -> node info from config/nav_map.json ({} if the file is missing)."""
    try:
        data = json.loads(_NAV_MAP.read_text())
    except (OSError, ValueError):
        return {}
    nodes = data.get("nodes", [])
    if isinstance(nodes, dict):
        return dict(nodes)
    out: dict[str, dict] = {}
    for entry in nodes:
        if isinstance(entry, (list, tuple)) and len(entry) == 2:
            out[entry[0]] = entry[1] or {}
        elif isinstance(entry, dict) and "id" in entry:
            out[entry["id"]] = entry
    return out


def field_to_node(name: str) -> str:
    """'Sunflower Field' -> 'sunflower_field'. Already-valid node ids pass through unchanged."""
    if not name:
        return ""
    raw = name.strip()
    if raw in nav_nodes():
        return raw
    key = raw.lower().replace("-", " ").replace("_", " ").strip()
    if key in _ALIASES:
        return _ALIASES[key]
    return key.replace(" ", "_")


def node_to_display(node_id: str) -> str:
    """'sunflower_field' -> 'Sunflower Field' (uses the nav map's display name when present)."""
    info = nav_nodes().get(node_id)
    if info and info.get("display"):
        return str(info["display"])
    return node_id.replace("_", " ").title()


def is_known_node(name: str) -> bool:
    return field_to_node(name) in nav_nodes()


def landmark_to_node(landmark: str) -> str | None:
    """'hive_exterior' -> 'hive_1_entrance'. Node ids map to themselves. None if unknown."""
    nodes = nav_nodes()
    if landmark in nodes:
        return landmark
    for node_id, info in nodes.items():
        if landmark in (info.get("landmarks") or []):
            return node_id
    return None


def field_nodes() -> list[str]:
    """Nav nodes that are farmable fields, in nav map order."""
    return [n for n in nav_nodes() if n.endswith(("_field", "_patch", "_forest"))]


def field_display_names() -> list[str]:
    return [node_to_display(n) for n in field_nodes()]
