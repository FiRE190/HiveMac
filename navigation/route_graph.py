"""
RouteGraph — structured representation of every traversal edge in BSS.

Where NavMap defines the raw graph topology (Dijkstra weights, nodes),
RouteGraph defines the EXECUTION CONTRACT for each directed edge:
  - What traversal type is it? (walk, cannon, jump_glide, …)
  - What is the expected duration (baseline + terrain)?
  - What anchor validates arrival?
  - What heading should the camera have when starting?
  - How many retries are allowed before escalation?
  - Are there alternate recovery edges?

This is the source of truth for building the primitive execution sequence
for each edge. RouteEdge is richer than NavEdge — it drives the planner's
traversal decisions, not just the pathfinder.

TraversalType enum:
  WALK          — standard WASD walk (heading-aligned)
  CANNON        — red/blue/yellow cannon launch
  JUMP_GLIDE    — jump + glider deployment
  JUMP          — single jump only
  RAMP_WALK     — walk with terrain multiplier for ramp grade
  DIAGONAL_WALK — diagonal key combo (e.g. "wd")

Public API:
    rg = get_route_graph()
    edge = rg.get("spawn_platform", "hive_1_entrance")
    all_edges = rg.edges_from("spawn_platform")
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from utils.logger import get_logger

log = get_logger(__name__)


class TraversalType(Enum):
    WALK          = "walk"
    DIAGONAL_WALK = "diagonal_walk"
    RAMP_WALK     = "ramp_walk"
    CANNON        = "cannon"
    JUMP_GLIDE    = "jump_glide"
    JUMP          = "jump"


@dataclass
class RouteEdge:
    """
    Execution contract for one directed traversal.

    from_anchor:        source AnchorRegistry node_id
    to_anchor:          destination AnchorRegistry node_id
    traversal_type:     how we move
    keys:               list of (key_combo, baseline_duration_sec) tuples
    expected_duration:  nominal traversal time at standard speed (sec)
    expected_heading:   camera heading to align to before starting (None = any)
    expected_terrain:   terrain name expected along this edge
    validation_anchor:  which anchor to use for arrival validation (usually to_anchor)
    arrival_landmark:   landmark template name to scan for during walk (perception stop)
    arrival_conf:       confidence threshold for perception-driven stop
    retry_limit:        max edge retries before escalating to RecoveryManager
    recovery_edges:     fallback edge keys (from → to) to try if this edge fails repeatedly
    cannon_key:         activation key for CANNON traversal (default "e")
    air_time_sec:       upper bound on cannon/glider air time
    cost:               path-planner weight (lower = preferred)
    """
    from_anchor:       str
    to_anchor:         str
    traversal_type:    TraversalType
    keys:              List[Tuple[str, float]]
    expected_duration: float
    expected_heading:  Optional[float]         = None
    expected_terrain:  str                     = "GROUND"
    validation_anchor: Optional[str]           = None
    arrival_landmark:  Optional[str]           = None
    arrival_conf:      float                   = 0.50
    retry_limit:       int                     = 2
    recovery_edges:    List[Tuple[str, str]]   = field(default_factory=list)
    cannon_key:        str                     = "e"
    air_time_sec:      float                   = 5.0
    cost:              float                   = 1.0

    def __post_init__(self) -> None:
        if self.validation_anchor is None:
            self.validation_anchor = self.to_anchor


# ── BSS edge definitions ───────────────────────────────────────────────────────
#
# expected_duration = baseline at 16 studs/s; MovementExecutor multiplies by
# TIMEOUT_MARGIN (2.5×) for the actual upper-bound timeout.
#
# Keys for diagonal walks are two-char strings: "wd" = W+D simultaneously.

_BSS_EDGES: List[RouteEdge] = [

    # ── Spawn area ──────────────────────────────────────────────────────────
    RouteEdge(
        from_anchor="spawn_platform",
        to_anchor="hive_1_entrance",
        traversal_type=TraversalType.WALK,
        keys=[("w", 2.5)],
        expected_duration=2.5,
        expected_heading=0.0,
        arrival_landmark="hive_exterior",
        arrival_conf=0.50,
        cost=1.0,
    ),
    RouteEdge(
        from_anchor="hive_1_entrance",
        to_anchor="spawn_platform",
        traversal_type=TraversalType.WALK,
        keys=[("s", 2.5)],
        expected_duration=2.5,
        expected_heading=180.0,
        arrival_landmark="spawn_platform",
        arrival_conf=0.45,
        cost=1.0,
    ),
    RouteEdge(
        from_anchor="spawn_platform",
        to_anchor="dandelion_field",
        traversal_type=TraversalType.DIAGONAL_WALK,
        keys=[("wd", 3.0)],
        expected_duration=3.0,
        expected_heading=45.0,
        arrival_landmark="dandelion_field",
        arrival_conf=0.45,
        cost=1.2,
    ),
    RouteEdge(
        from_anchor="dandelion_field",
        to_anchor="spawn_platform",
        traversal_type=TraversalType.DIAGONAL_WALK,
        keys=[("sa", 3.0)],
        expected_duration=3.0,
        expected_heading=225.0,
        arrival_landmark="spawn_platform",
        arrival_conf=0.45,
        cost=1.2,
    ),
    RouteEdge(
        from_anchor="spawn_platform",
        to_anchor="clover_field",
        traversal_type=TraversalType.DIAGONAL_WALK,
        keys=[("wa", 3.0)],
        expected_duration=3.0,
        expected_heading=315.0,
        arrival_landmark="clover_field",
        arrival_conf=0.45,
        cost=1.2,
    ),
    RouteEdge(
        from_anchor="clover_field",
        to_anchor="spawn_platform",
        traversal_type=TraversalType.DIAGONAL_WALK,
        keys=[("sd", 3.0)],
        expected_duration=3.0,
        expected_heading=135.0,
        arrival_landmark="spawn_platform",
        arrival_conf=0.45,
        cost=1.2,
    ),

    # ── Hive → Red Cannon ──────────────────────────────────────────────────
    RouteEdge(
        from_anchor="hive_1_entrance",
        to_anchor="red_cannon_pad",
        traversal_type=TraversalType.WALK,
        keys=[("d", 3.0)],
        expected_duration=3.0,
        expected_heading=90.0,
        arrival_landmark="red_cannon",
        arrival_conf=0.50,
        cost=1.0,
    ),
    RouteEdge(
        from_anchor="red_cannon_pad",
        to_anchor="hive_1_entrance",
        traversal_type=TraversalType.WALK,
        keys=[("a", 3.0)],
        expected_duration=3.0,
        expected_heading=270.0,
        arrival_landmark="hive_exterior",
        arrival_conf=0.50,
        cost=1.0,
    ),

    # ── Red Cannon → Sunflower Field (cannon launch) ───────────────────────
    RouteEdge(
        from_anchor="red_cannon_pad",
        to_anchor="sunflower_field",
        traversal_type=TraversalType.CANNON,
        keys=[],
        expected_duration=6.0,
        cannon_key="e",
        air_time_sec=6.0,
        arrival_landmark="sunflower_field",
        arrival_conf=0.45,
        cost=1.5,
    ),
    RouteEdge(
        from_anchor="sunflower_field",
        to_anchor="red_cannon_pad",
        traversal_type=TraversalType.RAMP_WALK,
        keys=[("s", 5.0)],
        expected_duration=5.0,
        expected_terrain="RAMP_DOWN",
        arrival_landmark="red_cannon",
        arrival_conf=0.45,
        cost=1.5,
    ),

    # ── Dandelion / Clover ↔ Hive ──────────────────────────────────────────
    RouteEdge(
        from_anchor="hive_1_entrance",
        to_anchor="dandelion_field",
        traversal_type=TraversalType.DIAGONAL_WALK,
        keys=[("wd", 3.0)],
        expected_duration=3.0,
        expected_heading=45.0,
        arrival_landmark="dandelion_field",
        arrival_conf=0.45,
        cost=1.0,
    ),
    RouteEdge(
        from_anchor="dandelion_field",
        to_anchor="hive_1_entrance",
        traversal_type=TraversalType.DIAGONAL_WALK,
        keys=[("sa", 3.0)],
        expected_duration=3.0,
        expected_heading=225.0,
        arrival_landmark="hive_exterior",
        arrival_conf=0.50,
        cost=1.0,
    ),
    RouteEdge(
        from_anchor="hive_1_entrance",
        to_anchor="clover_field",
        traversal_type=TraversalType.DIAGONAL_WALK,
        keys=[("wa", 3.0)],
        expected_duration=3.0,
        expected_heading=315.0,
        arrival_landmark="clover_field",
        arrival_conf=0.45,
        cost=1.0,
    ),
    RouteEdge(
        from_anchor="clover_field",
        to_anchor="hive_1_entrance",
        traversal_type=TraversalType.DIAGONAL_WALK,
        keys=[("sd", 3.0)],
        expected_duration=3.0,
        expected_heading=135.0,
        arrival_landmark="hive_exterior",
        arrival_conf=0.50,
        cost=1.0,
    ),

    # ── Hive → Wealth Clock ─────────────────────────────────────────────────
    RouteEdge(
        from_anchor="hive_1_entrance",
        to_anchor="wealth_clock",
        traversal_type=TraversalType.WALK,
        keys=[("w", 4.0), ("a", 1.5)],
        expected_duration=5.5,
        expected_heading=0.0,
        arrival_landmark="wealth_clock",
        arrival_conf=0.55,
        cost=2.0,
    ),
    RouteEdge(
        from_anchor="wealth_clock",
        to_anchor="hive_1_entrance",
        traversal_type=TraversalType.WALK,
        keys=[("d", 1.5), ("s", 4.0)],
        expected_duration=5.5,
        arrival_landmark="hive_exterior",
        arrival_conf=0.50,
        cost=2.0,
    ),

    # ── Upper Platform ──────────────────────────────────────────────────────
    RouteEdge(
        from_anchor="spawn_platform",
        to_anchor="upper_platform",
        traversal_type=TraversalType.RAMP_WALK,
        keys=[("w", 6.0)],
        expected_duration=6.0,
        expected_terrain="RAMP_UP",
        expected_heading=0.0,
        arrival_landmark="upper_platform",
        arrival_conf=0.35,
        cost=2.0,
    ),
    RouteEdge(
        from_anchor="upper_platform",
        to_anchor="spawn_platform",
        traversal_type=TraversalType.RAMP_WALK,
        keys=[("s", 6.0)],
        expected_duration=6.0,
        expected_terrain="RAMP_DOWN",
        arrival_landmark="spawn_platform",
        arrival_conf=0.45,
        cost=2.0,
    ),

    # ── Upper Platform → Far Fields ─────────────────────────────────────────
    RouteEdge(
        from_anchor="upper_platform",
        to_anchor="blue_flower_field",
        traversal_type=TraversalType.DIAGONAL_WALK,
        keys=[("wd", 4.0)],
        expected_duration=4.0,
        expected_heading=45.0,
        arrival_landmark="blue_flower_field",
        arrival_conf=0.45,
        cost=1.5,
    ),
    RouteEdge(
        from_anchor="blue_flower_field",
        to_anchor="upper_platform",
        traversal_type=TraversalType.DIAGONAL_WALK,
        keys=[("sa", 4.0)],
        expected_duration=4.0,
        arrival_landmark="upper_platform",
        arrival_conf=0.35,
        cost=1.5,
    ),
    RouteEdge(
        from_anchor="upper_platform",
        to_anchor="strawberry_field",
        traversal_type=TraversalType.WALK,
        keys=[("d", 4.0)],
        expected_duration=4.0,
        expected_heading=90.0,
        arrival_landmark="strawberry_field",
        arrival_conf=0.45,
        cost=1.5,
    ),
    RouteEdge(
        from_anchor="strawberry_field",
        to_anchor="upper_platform",
        traversal_type=TraversalType.WALK,
        keys=[("a", 4.0)],
        expected_duration=4.0,
        arrival_landmark="upper_platform",
        arrival_conf=0.35,
        cost=1.5,
    ),
    RouteEdge(
        from_anchor="upper_platform",
        to_anchor="bamboo_field",
        traversal_type=TraversalType.DIAGONAL_WALK,
        keys=[("wa", 5.0)],
        expected_duration=5.0,
        expected_heading=315.0,
        arrival_landmark="bamboo_field",
        arrival_conf=0.45,
        cost=1.5,
    ),
    RouteEdge(
        from_anchor="bamboo_field",
        to_anchor="upper_platform",
        traversal_type=TraversalType.DIAGONAL_WALK,
        keys=[("sd", 5.0)],
        expected_duration=5.0,
        arrival_landmark="upper_platform",
        arrival_conf=0.35,
        cost=1.5,
    ),
    RouteEdge(
        from_anchor="upper_platform",
        to_anchor="rose_field",
        traversal_type=TraversalType.WALK,
        keys=[("a", 5.0)],
        expected_duration=5.0,
        expected_heading=270.0,
        arrival_landmark="rose_field",
        arrival_conf=0.45,
        cost=1.5,
    ),
    RouteEdge(
        from_anchor="rose_field",
        to_anchor="upper_platform",
        traversal_type=TraversalType.WALK,
        keys=[("d", 5.0)],
        expected_duration=5.0,
        arrival_landmark="upper_platform",
        arrival_conf=0.35,
        cost=1.5,
    ),

    # ── Mushroom Field (via ramp from spawn) ────────────────────────────────
    RouteEdge(
        from_anchor="spawn_platform",
        to_anchor="mushroom_field",
        traversal_type=TraversalType.RAMP_WALK,
        keys=[("wa", 5.0)],
        expected_duration=5.0,
        expected_terrain="RAMP_UP",
        expected_heading=315.0,
        arrival_landmark="mushroom_platform",
        arrival_conf=0.45,
        cost=2.0,
    ),
    RouteEdge(
        from_anchor="mushroom_field",
        to_anchor="spawn_platform",
        traversal_type=TraversalType.RAMP_WALK,
        keys=[("sd", 5.0)],
        expected_duration=5.0,
        expected_terrain="RAMP_DOWN",
        arrival_landmark="spawn_platform",
        arrival_conf=0.45,
        cost=2.0,
    ),
]


@dataclass
class EdgeScore:
    """Runtime reliability score for one edge (updated after each traversal)."""
    edge_key:      str
    reliability:   float = 1.0   # [0, 1]; higher = prefer this edge
    success_count: int   = 0
    failure_count: int   = 0
    recovery_count: int  = 0
    last_updated:  float = field(default_factory=lambda: __import__("time").monotonic)

    @property
    def attempt_count(self) -> int:
        return self.success_count + self.failure_count

    @property
    def success_rate(self) -> float:
        if self.attempt_count == 0:
            return 1.0
        return self.success_count / self.attempt_count


class RouteGraph:
    """
    Registry of all traversal edge contracts with dynamic reliability scoring.

    Indexed by (from_anchor, to_anchor) for O(1) lookup.
    Thread-safe (read-only after init; add_edge() and update_edge_score() use lock).

    Dynamic scoring:
      update_edge_score() is called after each traversal by the navigator.
      reliability_score() returns the current score used by the path planner.
      Edges with low reliability are penalized in path planning (higher cost).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._edges: Dict[Tuple[str, str], RouteEdge] = {}
        self._scores: Dict[str, EdgeScore] = {}
        for edge in _BSS_EDGES:
            self._edges[(edge.from_anchor, edge.to_anchor)] = edge

    def get(self, from_anchor: str, to_anchor: str) -> Optional[RouteEdge]:
        with self._lock:
            return self._edges.get((from_anchor, to_anchor))

    def edges_from(self, from_anchor: str) -> List[RouteEdge]:
        """Return outgoing edges sorted by dynamic reliability (best first)."""
        with self._lock:
            edges = [e for (f, _), e in self._edges.items() if f == from_anchor]
        edges.sort(key=lambda e: self.reliability_score(
            f"{e.from_anchor}→{e.to_anchor}"
        ), reverse=True)
        return edges

    def edges_to(self, to_anchor: str) -> List[RouteEdge]:
        with self._lock:
            return [e for (_, t), e in self._edges.items() if t == to_anchor]

    def all_edges(self) -> List[RouteEdge]:
        with self._lock:
            return list(self._edges.values())

    def add_edge(self, edge: RouteEdge) -> None:
        with self._lock:
            key = (edge.from_anchor, edge.to_anchor)
            self._edges[key] = edge
            log.info("RouteGraph: registered edge %s → %s", edge.from_anchor, edge.to_anchor)

    # ------------------------------------------------------------------ #
    # Dynamic edge scoring                                                #
    # ------------------------------------------------------------------ #

    def update_edge_score(
        self,
        from_anchor: str,
        to_anchor: str,
        success: bool,
        recovered: bool = False,
    ) -> None:
        """Record one traversal outcome and update edge reliability."""
        key = f"{from_anchor}→{to_anchor}"
        with self._lock:
            if key not in self._scores:
                self._scores[key] = EdgeScore(edge_key=key)
            s = self._scores[key]
            if success:
                s.success_count += 1
            else:
                s.failure_count += 1
            if recovered:
                s.recovery_count += 1

            # EMA reliability update
            raw = s.success_rate * (1.0 - (s.recovery_count / max(s.attempt_count, 1)) * 0.3)
            s.reliability = 0.25 * raw + 0.75 * s.reliability
            import time as _t
            s.last_updated = _t.monotonic()

    def reliability_score(self, edge_key: str) -> float:
        """Return edge reliability [0, 1]. 1.0 for unknown edges (optimistic prior)."""
        with self._lock:
            s = self._scores.get(edge_key)
            if s is None or s.attempt_count < 3:
                return 1.0
            return s.reliability

    def dynamic_cost(self, from_anchor: str, to_anchor: str) -> float:
        """Return cost adjusted by dynamic reliability. Used by path planner."""
        edge = self.get(from_anchor, to_anchor)
        if edge is None:
            return float("inf")
        base_cost  = edge.cost
        reliability = self.reliability_score(f"{from_anchor}→{to_anchor}")
        # Penalty: unreliable edges become up to 3× more expensive
        penalty = 1.0 + (1.0 - reliability) * 2.0
        return base_cost * penalty

    def all_scores(self) -> Dict[str, EdgeScore]:
        with self._lock:
            return dict(self._scores)

    def __contains__(self, pair: Tuple[str, str]) -> bool:
        with self._lock:
            return pair in self._edges


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[RouteGraph] = None
_inst_lock = threading.Lock()


def get_route_graph() -> RouteGraph:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = RouteGraph()
    return _instance
