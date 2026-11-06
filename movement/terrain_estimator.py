"""
Real-time terrain type inference from optical-flow speed ratios.

The AdaptiveController measures instantaneous movement speed (px/s) via
Lucas-Kanade optical flow.  By comparing actual speed to the calibrated
flat-ground baseline we infer slope/elevation with no game API access:

  speed_ratio < 0.15  → STUCK     (wall / collision)
  ratio 0.15–0.60     → RAMP_UP   (uphill, player slowed)
  ratio 0.60–1.40     → GROUND    (flat terrain)
  ratio 1.40–2.50     → RAMP_DOWN (downhill, player faster)
  ratio > 2.50        → BOOST     (speed buff active)

A large vertical-flow fraction (|dy| / speed ≥ 0.40) alongside high speed
indicates the player is airborne (cannon launch, jump peak, glide).

The classifier keeps a 10-sample rolling window to smooth single-frame noise.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Deque, Optional

from movement.position_detector import MovementDelta


class TerrainType(Enum):
    GROUND    = auto()
    RAMP_UP   = auto()
    RAMP_DOWN = auto()
    BOOST     = auto()
    STUCK     = auto()
    AIRBORNE  = auto()


@dataclass
class TerrainSample:
    terrain:     TerrainType
    speed_ratio: float
    confidence:  float
    dy_fraction: float   # |dy| / speed — elevation indicator


class TerrainEstimator:
    """
    Sliding-window terrain classifier.

    Call update() after each movement delta.  Use current_terrain() to
    get the majority-vote terrain type across the last N samples.
    """

    _WINDOW     = 10

    _STUCK_T    = 0.15
    _RAMP_UP_T  = 0.60
    _RAMP_DN_T  = 1.40
    _BOOST_T    = 2.50
    _ELEV_T     = 0.40   # vertical fraction → airborne

    def __init__(self) -> None:
        self._history: Deque[TerrainSample] = deque(maxlen=self._WINDOW)
        self._base_speed: float = 0.0

    def set_base_speed(self, px_per_sec: float) -> None:
        self._base_speed = max(1.0, px_per_sec)

    def update(self, delta: Optional[MovementDelta]) -> TerrainSample:
        if delta is None or delta.confidence < 0.2 or self._base_speed < 1.0:
            sample = TerrainSample(TerrainType.GROUND, 1.0, 0.0, 0.0)
            self._history.append(sample)
            return sample

        ratio   = delta.speed / self._base_speed
        dy_frac = abs(delta.dy) / (delta.speed + 1e-6)

        if ratio < self._STUCK_T:
            terrain = TerrainType.STUCK
        elif ratio > self._BOOST_T:
            terrain = TerrainType.BOOST
        elif ratio > self._RAMP_DN_T:
            terrain = TerrainType.RAMP_DOWN
        elif ratio < self._RAMP_UP_T:
            terrain = TerrainType.RAMP_UP
        else:
            terrain = TerrainType.GROUND

        # High vertical fraction + fast speed → airborne
        if dy_frac > self._ELEV_T and ratio > 1.2:
            terrain = TerrainType.AIRBORNE

        sample = TerrainSample(terrain, ratio, delta.confidence, dy_frac)
        self._history.append(sample)
        return sample

    def current_terrain(self) -> TerrainType:
        if not self._history:
            return TerrainType.GROUND
        counts: dict[TerrainType, int] = {}
        for s in self._history:
            counts[s.terrain] = counts.get(s.terrain, 0) + 1
        return max(counts, key=lambda k: counts[k])

    def mean_speed_ratio(self) -> float:
        if not self._history:
            return 1.0
        valid = [s.speed_ratio for s in self._history if s.confidence > 0.2]
        return float(sum(valid) / len(valid)) if valid else 1.0

    def is_stuck(self) -> bool:
        if len(self._history) < 3:
            return False
        return all(s.terrain == TerrainType.STUCK for s in list(self._history)[-3:])

    def is_airborne(self) -> bool:
        return bool(self._history) and self._history[-1].terrain == TerrainType.AIRBORNE

    def reset(self) -> None:
        self._history.clear()
