"""
Navigation layer shared types.

Dependency rule: nothing here imports from other navigation modules.
All other navigation modules import FROM here.

Layer contracts:
    LandmarkReading  ← landmark_detector  →  localizer
    PositionEstimate ← localizer          →  navigator, path_planner
    NavNode / NavEdge← nav_map            →  path_planner, navigator
    NavPlan          ← path_planner       →  navigator
    EdgeResult       ← movement_executor  →  navigator
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Landmark sensing
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LandmarkReading:
    """One landmark sighting from a single frame."""
    name:        str
    confidence:  float              # 0–1; fused from template + color signals
    screen_rect: Tuple[int, int, int, int]  # (x, y, w, h) in screen pixels
    timestamp:   float = 0.0

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = time.monotonic()


# ─────────────────────────────────────────────────────────────────────────────
# Position estimation
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PositionEstimate:
    """
    Best-guess world position at a point in time.

    node_id       — the nav_map node we believe we're at (None = unknown)
    confidence    — 0: totally lost,  1: freshly anchored to landmark
    displacement  — dead-reckoning offset (pixels) since last anchor fix;
                    (dx, dy) in screen-flow coordinates
    timestamp     — monotonic time of last update
    """
    node_id:      Optional[str]        = None
    confidence:   float                = 0.0
    displacement: Tuple[float, float]  = (0.0, 0.0)
    timestamp:    float                = 0.0

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = time.monotonic()

    @property
    def is_lost(self) -> bool:
        return self.confidence < 0.25

    @property
    def age_sec(self) -> float:
        return time.monotonic() - self.timestamp


# ─────────────────────────────────────────────────────────────────────────────
# Map representation
# ─────────────────────────────────────────────────────────────────────────────

class EdgeMethod(Enum):
    WALK       = "walk"
    CANNON     = "cannon"
    GLIDER     = "glider"
    JUMP       = "jump"
    JUMP_GLIDE = "jump_glide"


class TerrainHint(Enum):
    GROUND    = "ground"
    RAMP_UP   = "ramp_up"
    RAMP_DOWN = "ramp_down"
    BRIDGE    = "bridge"
    PLATFORM  = "platform"


@dataclass
class NavNode:
    """A named, visually identifiable location in the BSS world."""
    node_id:    str
    display:    str                  # human-readable name
    landmarks:  List[str]            # landmark names visible from here
    description: str = ""


@dataclass
class NavEdge:
    """
    One directed traversal between two NavNodes.

    For WALK edges:
        keys = [("w", 2.0), ("d", 1.5)] — key + baseline duration (sec)
    For CANNON edges:
        cannon_key, cannon_align_keys, expected_air_time_sec
    For GLIDER edges:
        glider_key, expected_glide_sec
    """
    from_node:  str
    to_node:    str
    method:     EdgeMethod = EdgeMethod.WALK
    terrain:    TerrainHint = TerrainHint.GROUND

    # Walk parameters
    keys:       List[Tuple[str, float]] = field(default_factory=list)

    # Cannon parameters
    cannon_key:         str = "e"
    cannon_align_keys:  List[Tuple[str, float]] = field(default_factory=list)
    expected_air_time_sec: float = 4.0

    # Glider parameters
    glider_key:         str = "q"
    expected_glide_sec: float = 3.0

    # In-transit arrival detection (perception-driven stopping)
    # Landmark to scan for DURING movement — stops the walk early when detected.
    # Time durations in `keys` serve as UPPER BOUND TIMEOUTS only; the primary
    # stopping condition is this landmark reaching arrival_conf.
    arrival_landmark: Optional[str] = None
    arrival_conf: float = 0.50

    # Post-arrival checkpoint (existing behavior — verified after walk stops)
    checkpoint: Optional[str] = None
    checkpoint_conf: float = 0.55

    # Jump modifiers
    jump_at_start: bool = False
    jump_at_end:   bool = False

    # Estimated cost for path planning (lower = preferred)
    cost: float = 1.0

    # Fallback destination if this edge fails
    fallback: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Path planning
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NavPlan:
    """An ordered list of edges from current position to destination."""
    destination: str
    edges: List[NavEdge] = field(default_factory=list)
    total_cost: float = 0.0

    def __len__(self) -> int:
        return len(self.edges)


# ─────────────────────────────────────────────────────────────────────────────
# Execution results
# ─────────────────────────────────────────────────────────────────────────────

class EdgeStatus(Enum):
    SUCCESS    = auto()   # arrived, checkpoint verified
    UNVERIFIED = auto()   # arrived (timeout), checkpoint not confirmed
    STUCK      = auto()   # optical flow showed no progress
    FAILED     = auto()   # stop_event or hard failure
    LOST       = auto()   # arrived but checkpoint mismatch — position unknown


@dataclass
class EdgeResult:
    status:     EdgeStatus
    edge:       NavEdge
    elapsed_sec: float = 0.0
    checkpoint_confidence: float = 0.0
    message:    str = ""
