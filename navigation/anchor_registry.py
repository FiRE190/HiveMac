"""
AnchorRegistry — visual and physical characterization of every named BSS location.

An anchor is a deterministic, visually identifiable position in the world.
Where NavMap defines the GRAPH topology (nodes + edges), AnchorRegistry defines
what each node LOOKS LIKE from the player's perspective so the runtime can:

  1. Confirm it has arrived at an expected location (checkpoint validation)
  2. Identify its current location during recovery (reorientation scan)
  3. Know what camera heading to expect at each location
  4. Know what terrain type to expect when standing at each location

AnchorDefinition fields:
  template_groups    — perception/template_system.py group names to match for this anchor
  landmark_names     — individual landmark names (from landmark_detector HSV profiles)
  expected_heading   — camera heading after F-reset and arriving here (None = any)
  heading_tolerance  — degrees of acceptable heading error
  expected_terrain   — set of TerrainType names valid when standing here
  neighboring_anchors— adjacent nodes; used to narrow recovery scan scope
  recovery_priority  — lower = scan this anchor first when lost (1 = highest priority)
  min_confidence     — minimum fused confidence to count as a match

The registry is keyed by node_id — the same IDs used in nav_map.json.

Public API:
    reg = get_anchor_registry()
    anchor = reg.get("hive_1_entrance")    # AnchorDefinition or None
    ordered = reg.recovery_order()         # sorted by recovery_priority
    candidates = reg.neighbors_of("spawn_platform")
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class AnchorDefinition:
    """
    Visual and physical characterization of one navigation anchor.

    This is the ground-truth description of what the runtime should observe
    when it is standing at this location.
    """
    id:                  str
    display:             str
    template_groups:     List[str]        # template_system group names
    landmark_names:      List[str]        # landmark_detector individual names
    expected_heading:    Optional[float]  # camera heading in degrees (None = any)
    heading_tolerance:   float            # acceptable heading error in degrees
    expected_terrain:    Set[str]         # TerrainType.name values
    neighboring_anchors: List[str]        # node_ids of adjacent locations
    recovery_priority:   int              # 1 = highest; lower = scan first
    min_confidence:      float            # minimum to accept this as confirmed
    description:         str              = ""

    def matches_terrain(self, terrain_name: str) -> bool:
        return terrain_name in self.expected_terrain

    def heading_ok(self, heading_deg: float) -> bool:
        if self.expected_heading is None:
            return True
        diff = abs((heading_deg - self.expected_heading + 180.0) % 360.0 - 180.0)
        return diff <= self.heading_tolerance


# ── BSS anchor definitions ─────────────────────────────────────────────────────
#
# expected_heading = 0.0 means "camera at default F-reset forward position."
# All headings are degrees from the post-F-reset forward direction.
#
# These are starting estimates — the heading model will refine them with optical
# flow. heading_tolerance is generous (25–45°) to account for model uncertainty.

_BSS_ANCHORS: Dict[str, AnchorDefinition] = {

    "spawn_platform": AnchorDefinition(
        id="spawn_platform",
        display="Spawn Platform",
        template_groups=["navigation_anchors"],
        landmark_names=["spawn_platform"],
        expected_heading=0.0,
        heading_tolerance=30.0,
        expected_terrain={"GROUND", "RAMP_DOWN"},
        neighboring_anchors=["hive_1_entrance", "dandelion_field", "clover_field"],
        recovery_priority=1,
        min_confidence=0.45,
        description="Player spawn area — visible after death/respawn",
    ),

    "hive_1_entrance": AnchorDefinition(
        id="hive_1_entrance",
        display="Hive 1 Entrance",
        template_groups=["hive_indicators", "navigation_anchors"],
        landmark_names=["hive_exterior"],
        expected_heading=0.0,
        heading_tolerance=45.0,
        expected_terrain={"GROUND"},
        neighboring_anchors=["spawn_platform", "red_cannon_pad", "dandelion_field", "clover_field"],
        recovery_priority=2,
        min_confidence=0.45,
        description="Ground level in front of the first hive",
    ),

    "red_cannon_pad": AnchorDefinition(
        id="red_cannon_pad",
        display="Red Cannon Platform",
        template_groups=["navigation_anchors"],
        landmark_names=["red_cannon"],
        expected_heading=None,
        heading_tolerance=45.0,
        expected_terrain={"GROUND", "RAMP_DOWN"},
        neighboring_anchors=["hive_1_entrance", "sunflower_field"],
        recovery_priority=3,
        min_confidence=0.50,
        description="Red cannon launch platform near hive",
    ),

    "dandelion_field": AnchorDefinition(
        id="dandelion_field",
        display="Dandelion Field",
        template_groups=["field_identifiers"],
        landmark_names=["dandelion_field"],
        expected_heading=None,
        heading_tolerance=45.0,
        expected_terrain={"GROUND"},
        neighboring_anchors=["spawn_platform", "hive_1_entrance"],
        recovery_priority=4,
        min_confidence=0.45,
        description="White dandelion field near spawn",
    ),

    "sunflower_field": AnchorDefinition(
        id="sunflower_field",
        display="Sunflower Field",
        template_groups=["field_identifiers"],
        landmark_names=["sunflower_field"],
        expected_heading=None,
        heading_tolerance=45.0,
        expected_terrain={"GROUND"},
        neighboring_anchors=["red_cannon_pad"],
        recovery_priority=5,
        min_confidence=0.45,
        description="Sunflower field past red cannon",
    ),

    "clover_field": AnchorDefinition(
        id="clover_field",
        display="Clover Field",
        template_groups=["field_identifiers"],
        landmark_names=["clover_field"],
        expected_heading=None,
        heading_tolerance=45.0,
        expected_terrain={"GROUND"},
        neighboring_anchors=["spawn_platform", "hive_1_entrance"],
        recovery_priority=6,
        min_confidence=0.45,
        description="Clover field near hive complex",
    ),

    "blue_flower_field": AnchorDefinition(
        id="blue_flower_field",
        display="Blue Flower Field",
        template_groups=["field_identifiers"],
        landmark_names=["blue_flower_field"],
        expected_heading=None,
        heading_tolerance=45.0,
        expected_terrain={"GROUND"},
        neighboring_anchors=["upper_platform"],
        recovery_priority=7,
        min_confidence=0.45,
        description="Blue flower field — via upper platform diagonal",
    ),

    "mushroom_field": AnchorDefinition(
        id="mushroom_field",
        display="Mushroom Field",
        template_groups=["field_identifiers"],
        landmark_names=["mushroom_platform"],
        expected_heading=None,
        heading_tolerance=45.0,
        expected_terrain={"GROUND", "RAMP_UP"},
        neighboring_anchors=["spawn_platform"],
        recovery_priority=8,
        min_confidence=0.45,
        description="Field on top of the large mushroom platform",
    ),

    "strawberry_field": AnchorDefinition(
        id="strawberry_field",
        display="Strawberry Field",
        template_groups=["field_identifiers"],
        landmark_names=["strawberry_field"],
        expected_heading=None,
        heading_tolerance=45.0,
        expected_terrain={"GROUND"},
        neighboring_anchors=["upper_platform"],
        recovery_priority=9,
        min_confidence=0.45,
        description="Strawberry field via upper platform",
    ),

    "bamboo_field": AnchorDefinition(
        id="bamboo_field",
        display="Bamboo Field",
        template_groups=["field_identifiers"],
        landmark_names=["bamboo_field"],
        expected_heading=None,
        heading_tolerance=45.0,
        expected_terrain={"GROUND"},
        neighboring_anchors=["upper_platform"],
        recovery_priority=10,
        min_confidence=0.45,
        description="Bamboo field via upper platform diagonal",
    ),

    "stump_field": AnchorDefinition(
        id="stump_field",
        display="Stump Field",
        template_groups=["field_identifiers"],
        landmark_names=["stump_field"],
        expected_heading=None,
        heading_tolerance=45.0,
        expected_terrain={"GROUND", "RAMP_UP"},
        neighboring_anchors=["upper_platform"],
        recovery_priority=11,
        min_confidence=0.45,
        description="Field on top of the giant tree stump",
    ),

    "spider_field": AnchorDefinition(
        id="spider_field",
        display="Spider Field",
        template_groups=["field_identifiers"],
        landmark_names=["spider_field"],
        expected_heading=None,
        heading_tolerance=45.0,
        expected_terrain={"GROUND"},
        neighboring_anchors=["upper_platform"],
        recovery_priority=12,
        min_confidence=0.45,
        description="Dark spider-infested field via upper platform",
    ),

    "rose_field": AnchorDefinition(
        id="rose_field",
        display="Rose Field",
        template_groups=["field_identifiers"],
        landmark_names=["rose_field"],
        expected_heading=None,
        heading_tolerance=45.0,
        expected_terrain={"GROUND"},
        neighboring_anchors=["upper_platform"],
        recovery_priority=13,
        min_confidence=0.45,
        description="Rose field via upper platform",
    ),

    "pineapple_patch": AnchorDefinition(
        id="pineapple_patch",
        display="Pineapple Patch",
        template_groups=["field_identifiers"],
        landmark_names=["pineapple_patch"],
        expected_heading=None,
        heading_tolerance=45.0,
        expected_terrain={"GROUND"},
        neighboring_anchors=["upper_platform"],
        recovery_priority=14,
        min_confidence=0.45,
        description="Pineapple patch via upper platform",
    ),

    "pine_tree_forest": AnchorDefinition(
        id="pine_tree_forest",
        display="Pine Tree Forest",
        template_groups=["field_identifiers"],
        landmark_names=["pine_tree_forest"],
        expected_heading=None,
        heading_tolerance=45.0,
        expected_terrain={"GROUND"},
        neighboring_anchors=["upper_platform"],
        recovery_priority=15,
        min_confidence=0.45,
        description="Pine tree forest via upper platform",
    ),

    "upper_platform": AnchorDefinition(
        id="upper_platform",
        display="Upper Platform",
        template_groups=["navigation_anchors"],
        landmark_names=["upper_platform"],
        expected_heading=None,
        heading_tolerance=45.0,
        expected_terrain={"GROUND", "RAMP_UP"},
        neighboring_anchors=[
            "blue_flower_field", "strawberry_field", "bamboo_field",
            "stump_field", "spider_field", "rose_field",
        ],
        recovery_priority=3,
        min_confidence=0.35,
        description="Elevated platform — gateway to far fields (no template yet)",
    ),

    "wealth_clock": AnchorDefinition(
        id="wealth_clock",
        display="Wealth Clock",
        template_groups=["wealth_clock_indicators"],
        landmark_names=[],
        expected_heading=None,
        heading_tolerance=45.0,
        expected_terrain={"GROUND"},
        neighboring_anchors=["hive_1_entrance"],
        recovery_priority=16,
        min_confidence=0.55,
        description="Wealth clock platform",
    ),
}


class AnchorRegistry:
    """
    Immutable registry of BSS anchor definitions.

    Thread-safe (read-only after init; add_anchor() is the only mutator and
    uses a lock).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._anchors: Dict[str, AnchorDefinition] = dict(_BSS_ANCHORS)

    def get(self, anchor_id: str) -> Optional[AnchorDefinition]:
        with self._lock:
            return self._anchors.get(anchor_id)

    def all(self) -> List[AnchorDefinition]:
        with self._lock:
            return list(self._anchors.values())

    def recovery_order(self) -> List[AnchorDefinition]:
        """All anchors sorted by recovery_priority (lowest first = try first)."""
        with self._lock:
            return sorted(self._anchors.values(), key=lambda a: a.recovery_priority)

    def neighbors_of(self, anchor_id: str) -> List[AnchorDefinition]:
        """Return AnchorDefinitions for all anchors neighboring the given one."""
        anchor = self.get(anchor_id)
        if not anchor:
            return []
        with self._lock:
            return [self._anchors[n] for n in anchor.neighboring_anchors if n in self._anchors]

    def add_anchor(self, anchor: AnchorDefinition) -> None:
        """Register a new anchor (or overwrite existing). Use for calibration tool."""
        with self._lock:
            self._anchors[anchor.id] = anchor
            log.info("AnchorRegistry: registered '%s'", anchor.id)

    def __contains__(self, anchor_id: str) -> bool:
        with self._lock:
            return anchor_id in self._anchors

    def __len__(self) -> int:
        with self._lock:
            return len(self._anchors)


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[AnchorRegistry] = None
_inst_lock = threading.Lock()


def get_anchor_registry() -> AnchorRegistry:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = AnchorRegistry()
    return _instance
