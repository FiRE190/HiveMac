"""
NavMap — world graph for Bee Swarm Simulator navigation.

Loads from config/nav_map.json.  Provides:
  - Node lookup by ID
  - Edge lookup (from_node → [NavEdge])
  - Landmark → node reverse mapping (used by Localizer)
  - Hot-reload for the calibration tool

On first load the map is populated with BSS defaults for common destinations.
The user overrides specific durations via the calibration tool which writes
back to nav_map.json.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, List, Optional

from navigation.types import NavNode, NavEdge, EdgeMethod, TerrainHint
from navigation.localizer import init_localizer
from utils.logger import get_logger

log = get_logger(__name__)

_MAP_FILE = Path(__file__).parent.parent / "config" / "nav_map.json"


class NavMap:
    """
    Thread-safe world graph.

    Call get_nav_map() to get the singleton; the constructor loads the file
    and initialises the Localizer's landmark→node mapping.
    """

    def __init__(self) -> None:
        self._lock  = threading.RLock()
        self._nodes: Dict[str, NavNode] = {}
        self._edges: Dict[str, List[NavEdge]] = {}   # from_node → [NavEdge]
        self._load()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def get_node(self, node_id: str) -> Optional[NavNode]:
        with self._lock:
            return self._nodes.get(node_id)

    def get_edges_from(self, node_id: str) -> List[NavEdge]:
        with self._lock:
            return list(self._edges.get(node_id, []))

    def has_node(self, node_id: str) -> bool:
        with self._lock:
            return node_id in self._nodes

    def all_nodes(self) -> List[str]:
        with self._lock:
            return list(self._nodes.keys())

    def all_landmarks(self) -> List[str]:
        """All landmark names referenced in the map."""
        seen: set[str] = set()
        with self._lock:
            for node in self._nodes.values():
                seen.update(node.landmarks)
        return list(seen)

    def node_for_landmark(self, landmark: str) -> Optional[str]:
        """Return the single node that lists this landmark (None if ambiguous)."""
        with self._lock:
            candidates = [
                nid for nid, node in self._nodes.items()
                if landmark in node.landmarks
            ]
        return candidates[0] if len(candidates) == 1 else None

    def landmark_to_nodes_map(self) -> Dict[str, List[str]]:
        """Build the landmark→[node_id] map for the Localizer."""
        result: Dict[str, List[str]] = {}
        with self._lock:
            for nid, node in self._nodes.items():
                for lm in node.landmarks:
                    result.setdefault(lm, []).append(nid)
        return result

    def reload(self) -> None:
        with self._lock:
            self._nodes.clear()
            self._edges.clear()
            self._load()
        log.info("NavMap reloaded from %s", _MAP_FILE)

    # ------------------------------------------------------------------ #
    # Load / parse                                                         #
    # ------------------------------------------------------------------ #

    def _load(self) -> None:
        if not _MAP_FILE.exists():
            log.warning("nav_map.json not found — using empty graph")
            self._reinit_localizer()
            return

        try:
            with open(_MAP_FILE, "r") as fh:
                data = json.load(fh)
        except Exception as exc:
            log.error("NavMap load error: %s", exc)
            self._reinit_localizer()
            return

        for node_id, nd in data.get("nodes", {}).items():
            self._nodes[node_id] = NavNode(
                node_id=node_id,
                display=nd.get("display", node_id),
                landmarks=nd.get("landmarks", []),
                description=nd.get("description", ""),
            )

        for ed in data.get("edges", []):
            edge = self._parse_edge(ed)
            if edge:
                self._edges.setdefault(edge.from_node, []).append(edge)

        log.info("NavMap: %d nodes, %d from-nodes loaded",
                 len(self._nodes), len(self._edges))
        self._reinit_localizer()

    def _parse_edge(self, ed: dict) -> Optional[NavEdge]:
        try:
            method  = EdgeMethod(ed.get("method", "walk"))
            terrain = TerrainHint(ed.get("terrain", "ground"))
            keys    = [(k, float(d)) for k, d in ed.get("keys", [])]
            align   = [(k, float(d)) for k, d in ed.get("cannon_align_keys", [])]
            return NavEdge(
                from_node=ed["from"],
                to_node=ed["to"],
                method=method,
                terrain=terrain,
                keys=keys,
                cannon_key=ed.get("cannon_key", "e"),
                cannon_align_keys=align,
                expected_air_time_sec=float(ed.get("expected_air_time_sec", 4.0)),
                glider_key=ed.get("glider_key", "q"),
                expected_glide_sec=float(ed.get("expected_glide_sec", 3.0)),
                arrival_landmark=ed.get("arrival_landmark"),
                arrival_conf=float(ed.get("arrival_conf", 0.50)),
                checkpoint=ed.get("checkpoint"),
                checkpoint_conf=float(ed.get("checkpoint_conf", 0.55)),
                jump_at_start=bool(ed.get("jump_at_start", False)),
                jump_at_end=bool(ed.get("jump_at_end", False)),
                cost=float(ed.get("cost", 1.0)),
                fallback=ed.get("fallback"),
            )
        except Exception as exc:
            log.warning("NavMap: skipping bad edge %s: %s", ed, exc)
            return None

    def _reinit_localizer(self) -> None:
        """Push the new landmark→node map into the Localizer singleton."""
        init_localizer(self.landmark_to_nodes_map())


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[NavMap] = None
_inst_lock = threading.Lock()


def get_nav_map() -> NavMap:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = NavMap()
    return _instance
