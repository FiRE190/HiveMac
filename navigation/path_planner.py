"""
Path planner — Dijkstra shortest-path over the NavMap world graph.

Given a current node_id and a destination node_id, computes the minimum-cost
sequence of NavEdges to traverse.

Design notes:
  - Uses standard Dijkstra (graph is small; A* offers no practical advantage)
  - Edge cost is NavEdge.cost (data-driven, not geometric distance)
  - If current_node is None (lost) the planner cannot produce a plan
  - Produces NavPlan(destination, edges, total_cost)
  - Returns None when no path exists

Public API:
    planner = get_path_planner()
    plan = planner.plan("hive_1_entrance", "sunflower_field")
    if plan:
        for edge in plan.edges: ...
"""
from __future__ import annotations

import heapq
import threading
from typing import Dict, List, Optional

from navigation.nav_map import get_nav_map
from navigation.types import NavEdge, NavPlan
from utils.logger import get_logger

log = get_logger(__name__)


class PathPlanner:
    """
    Stateless Dijkstra planner over the NavMap.

    Thread-safe (no mutable state; NavMap access is guarded by NavMap's lock).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def plan(
        self,
        from_node: Optional[str],
        to_node: str,
    ) -> Optional[NavPlan]:
        """
        Compute the lowest-cost path from from_node to to_node.

        Returns None when:
          - from_node is None (position unknown)
          - to_node doesn't exist in the map
          - No path exists between from_node and to_node
        """
        if from_node is None:
            log.debug("PathPlanner: cannot plan — current node unknown")
            return None

        nav = get_nav_map()
        if not nav.has_node(to_node):
            log.warning("PathPlanner: destination '%s' not in map", to_node)
            return None
        if from_node == to_node:
            return NavPlan(destination=to_node, edges=[], total_cost=0.0)
        if not nav.has_node(from_node):
            log.warning("PathPlanner: from_node '%s' not in map", from_node)
            return None

        return self._dijkstra(from_node, to_node, nav)

    def _dijkstra(self, start: str, goal: str, nav) -> Optional[NavPlan]:
        dist:  Dict[str, float]           = {start: 0.0}
        prev:  Dict[str, Optional[str]]   = {start: None}
        edges_used: Dict[str, Optional[NavEdge]] = {start: None}

        # (cost, node_id)
        heap: List = [(0.0, start)]

        while heap:
            cost, node = heapq.heappop(heap)
            if cost > dist.get(node, float("inf")):
                continue  # stale entry
            if node == goal:
                return self._reconstruct(goal, dist, prev, edges_used)

            for edge in nav.get_edges_from(node):
                new_cost = cost + edge.cost
                if new_cost < dist.get(edge.to_node, float("inf")):
                    dist[edge.to_node]       = new_cost
                    prev[edge.to_node]       = node
                    edges_used[edge.to_node] = edge
                    heapq.heappush(heap, (new_cost, edge.to_node))

        log.warning("PathPlanner: no path from '%s' to '%s'", start, goal)
        return None

    def _reconstruct(
        self,
        goal: str,
        dist: Dict[str, float],
        prev: Dict[str, Optional[str]],
        edges_used: Dict[str, Optional[NavEdge]],
    ) -> NavPlan:
        path_edges: List[NavEdge] = []
        node = goal
        while prev.get(node) is not None:
            edge = edges_used[node]
            if edge:
                path_edges.append(edge)
            node = prev[node]  # type: ignore[assignment]
        path_edges.reverse()
        total = dist.get(goal, 0.0)
        log.debug(
            "PathPlanner: %d-edge path to '%s' (cost=%.2f)",
            len(path_edges), goal, total,
        )
        return NavPlan(destination=goal, edges=path_edges, total_cost=total)


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[PathPlanner] = None
_inst_lock = threading.Lock()


def get_path_planner() -> PathPlanner:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = PathPlanner()
    return _instance
