"""
Localizer — position estimation for the navigation stack.

Fuses two information sources:
  1. Landmark observations  — discrete high-confidence fixes
  2. Dead reckoning         — continuous low-confidence displacement tracking
                              via optical-flow accumulated displacement

Design:
  - Each landmark sighting anchors us to the node(s) that list that landmark.
  - Between sightings, optical-flow displacement accumulates as dead reckoning.
  - Confidence decays with dead-reckoning distance (more drift = less certain).
  - snap_to() forces position to a known node (after cannon landing, respawn).
  - After _LOST_AGE_SEC without an anchor update, position is considered lost.

Public API:
    loc = get_localizer()
    loc.observe(reading)                  # from LandmarkDetector
    loc.update_dead_reckoning(delta)      # from PositionDetector
    loc.snap_to("hive_1_entrance")       # forced anchor
    loc.reset()                           # full reset (respawn)
    est = loc.estimate                    # PositionEstimate
"""
from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional

from navigation.types import LandmarkReading, PositionEstimate
from utils.logger import get_logger

log = get_logger(__name__)

# Confidence below which we consider ourselves lost
_LOST_THRESHOLD = 0.25
# Age in seconds after which dead reckoning alone can't sustain confidence
_LOST_AGE_SEC = 45.0
# Dead reckoning: confidence decay per pixel of displacement (lower = faster decay)
_DR_DECAY_PER_PX = 0.002
# Minimum landmark confidence to trigger an anchor update
_ANCHOR_MIN_CONF = 0.50


class Localizer:
    """
    Thread-safe position estimator.

    Call observe() when the landmark detector finds something.
    Call update_dead_reckoning() every tick with the latest MovementDelta.
    Read estimate to get the current PositionEstimate.
    """

    def __init__(self, landmark_to_nodes: Dict[str, List[str]]) -> None:
        """
        landmark_to_nodes: mapping from landmark name → list of node_ids
        that are identifiable by that landmark.
        Provided by NavMap.
        """
        self._lm_to_nodes = landmark_to_nodes
        self._lock = threading.RLock()
        self._est  = PositionEstimate()
        self._dr_dx = 0.0   # dead-reckoning accumulated displacement
        self._dr_dy = 0.0

    # ------------------------------------------------------------------ #
    # Landmark observation                                                 #
    # ------------------------------------------------------------------ #

    def observe(self, reading: LandmarkReading) -> None:
        """
        Process a landmark sighting.

        If the landmark maps to exactly one node, update our position estimate.
        If it maps to multiple nodes (ambiguous), we raise confidence without
        committing to a specific node.
        """
        if reading.confidence < _ANCHOR_MIN_CONF:
            return

        nodes = self._lm_to_nodes.get(reading.name, [])
        with self._lock:
            if len(nodes) == 1:
                node_id = nodes[0]
                log.debug("Localizer: anchor → %s (landmark=%s conf=%.2f)",
                          node_id, reading.name, reading.confidence)
                self._est = PositionEstimate(
                    node_id=node_id,
                    confidence=reading.confidence,
                    displacement=(0.0, 0.0),
                )
                self._dr_dx = 0.0
                self._dr_dy = 0.0
            elif len(nodes) > 1:
                # Ambiguous landmark: boost confidence if any candidate matches
                # current node, otherwise raise as weak signal
                best_conf = min(reading.confidence * 0.70, 0.80)
                if self._est.node_id in nodes:
                    new_conf = max(self._est.confidence, best_conf)
                    self._est = PositionEstimate(
                        node_id=self._est.node_id,
                        confidence=new_conf,
                        displacement=self._est.displacement,
                    )
                else:
                    new_conf = max(self._est.confidence, best_conf * 0.50)
                    self._est = PositionEstimate(
                        node_id=self._est.node_id,
                        confidence=new_conf,
                        displacement=self._est.displacement,
                    )

    # ------------------------------------------------------------------ #
    # Dead reckoning                                                       #
    # ------------------------------------------------------------------ #

    def update_dead_reckoning(self, dx: float, dy: float) -> None:
        """
        Accumulate displacement and degrade confidence.

        dx, dy are screen-pixel velocities from PositionDetector (px/s).
        Call every tick with elapsed time already factored in (px moved this tick).
        """
        with self._lock:
            self._dr_dx += dx
            self._dr_dy += dy
            dist = (self._dr_dx ** 2 + self._dr_dy ** 2) ** 0.5

            # Degrade confidence proportional to distance drifted since last fix
            decay = dist * _DR_DECAY_PER_PX
            new_conf = max(0.0, self._est.confidence - decay)

            # Also degrade by age
            age = self._est.age_sec
            if age > _LOST_AGE_SEC:
                new_conf = max(0.0, new_conf - 0.01)

            self._est = PositionEstimate(
                node_id=self._est.node_id,
                confidence=new_conf,
                displacement=(self._dr_dx, self._dr_dy),
            )

    # ------------------------------------------------------------------ #
    # Forced anchoring                                                     #
    # ------------------------------------------------------------------ #

    def snap_to(self, node_id: str, confidence: float = 0.95) -> None:
        """
        Force position to a known node.

        Call after:
          - Cannon landing (we know we arrived at cannon destination)
          - Respawn (we know we're at spawn_platform)
          - Arrival verified by checkpoint (we confirmed we're at the destination)
        """
        with self._lock:
            log.debug("Localizer: snap → %s (conf=%.2f)", node_id, confidence)
            self._est = PositionEstimate(
                node_id=node_id,
                confidence=confidence,
                displacement=(0.0, 0.0),
            )
            self._dr_dx = 0.0
            self._dr_dy = 0.0

    def reset(self) -> None:
        """Full reset — call on death/respawn before snap_to("spawn_platform")."""
        with self._lock:
            self._est   = PositionEstimate()
            self._dr_dx = 0.0
            self._dr_dy = 0.0

    # ------------------------------------------------------------------ #
    # Read                                                                 #
    # ------------------------------------------------------------------ #

    @property
    def estimate(self) -> PositionEstimate:
        with self._lock:
            return self._est

    @property
    def is_lost(self) -> bool:
        with self._lock:
            return self._est.confidence < _LOST_THRESHOLD

    @property
    def current_node(self) -> Optional[str]:
        with self._lock:
            return self._est.node_id

    def confidence(self) -> float:
        with self._lock:
            return self._est.confidence


# ── Module-level singleton (created by NavMap after it builds the LM→node map)

_instance: Optional[Localizer] = None
_inst_lock = threading.Lock()


def get_localizer() -> Localizer:
    global _instance
    with _inst_lock:
        if _instance is None:
            # Bootstrap with empty map — NavMap will reinitialize
            _instance = Localizer({})
    return _instance


def init_localizer(landmark_to_nodes: Dict[str, List[str]]) -> Localizer:
    """Called by NavMap after loading the world graph."""
    global _instance
    with _inst_lock:
        _instance = Localizer(landmark_to_nodes)
    return _instance
