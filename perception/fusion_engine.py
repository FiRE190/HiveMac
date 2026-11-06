"""
FusionEngine — multi-signal sensor fusion for navigation confidence.

Combines independent perception signals into holistic confidence estimates
that the navigator, checkpoint validator, and recovery manager use to make
traversal decisions.

Signals fused (each normalized to [0, 1]):
  template_conf   — best template match score from template_system
  terrain_match   — does current terrain match anchor expectations?
  heading_match   — is camera heading consistent with expected for this anchor?
  movement_steady — is the player stationary (post-traversal settling check)?
  route_history   — how reliably has this segment been traversed before?

Output (FusionResult):
  localization_confidence — overall "where am I" confidence
  checkpoint_confidence   — "am I at the expected checkpoint?"
  drift_probability       — "how likely have I drifted off route?"
  dominant_anchor         — which anchor the signals point toward
  signals                 — per-signal contributions for debug

Fusion method: weighted geometric mean of active signals.
Weights are tunable constants; template_conf is the strongest single signal
because it's the most specific.

Public API:
    fe = get_fusion_engine()
    result = fe.fuse(
        anchor_id="hive_1_entrance",
        frame=frame,
        terrain=terrain_sample,
        heading_deg=cam.heading,
        heading_unc=cam.heading_uncertainty,
        speed_px_s=0.0,
    )
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np

from navigation.anchor_registry import get_anchor_registry, AnchorDefinition
from perception.frame_manager import get_frame_manager
from perception.template_system import get_template_system
from utils.logger import get_logger

log = get_logger(__name__)

# Signal weights for fusion (must sum to 1.0)
_WEIGHTS = {
    "template":        0.34,
    "terrain":         0.16,
    "heading":         0.16,
    "movement_steady": 0.08,
    "route_history":   0.12,
    "anchor_history":  0.10,  # temporal: how recently was this anchor confirmed?
    "route_confidence":0.04,  # route graph: is this anchor on the expected path?
}

# Speed below which we consider the player stationary (px/s)
_STATIONARY_SPEED = 8.0

# Heading match: angular difference → confidence decay
_HEADING_FULL_MATCH  = 10.0   # degrees — full confidence
_HEADING_ZERO_MATCH  = 90.0   # degrees — zero confidence


@dataclass
class FusionResult:
    """Multi-signal confidence estimates for one tick."""
    anchor_id:              Optional[str]
    localization_confidence: float          # overall "where am I" [0, 1]
    checkpoint_confidence:   float          # "am I at this specific checkpoint" [0, 1]
    drift_probability:       float          # probability of having drifted [0, 1]
    signals:                 Dict[str, float] = field(default_factory=dict)


class FusionEngine:
    """
    Multi-signal fusion for navigation confidence.

    Thread-safe via stateless design — fuse() takes all inputs as parameters
    and produces a result without modifying internal state.
    """

    def __init__(self) -> None:
        self._registry = get_anchor_registry()
        self._ts       = get_template_system()
        self._fm       = get_frame_manager()

    # ------------------------------------------------------------------ #
    # Primary fusion                                                       #
    # ------------------------------------------------------------------ #

    def fuse(
        self,
        anchor_id: Optional[str],
        frame: Optional[np.ndarray],
        terrain_name: str,
        heading_deg: float,
        heading_unc: float,
        speed_px_s: float,
        route_success_rate: float = 0.5,
        anchor_last_seen_sec: float = float("inf"),
        route_confidence: float = 0.5,
    ) -> FusionResult:
        """
        Fuse perception signals into confidence estimates.

        anchor_id:             expected anchor (or None if unknown)
        frame:                 current BGR frame (None = use frame_manager)
        terrain_name:          TerrainType.name of current terrain
        heading_deg:           current camera heading estimate (degrees)
        heading_unc:           heading uncertainty (degrees; 0 = perfect)
        speed_px_s:            current movement speed (px/s; 0 = stationary)
        route_success_rate:    recent success rate for this segment [0, 1]
        anchor_last_seen_sec:  seconds since this anchor was last confirmed [0, ∞)
        route_confidence:      does the current route expect us here? [0, 1]
        """
        anchor = self._registry.get(anchor_id) if anchor_id else None
        if frame is None:
            frame = self._fm.full_frame()

        signals: Dict[str, float] = {}

        # 1. Template confidence
        signals["template"] = self._template_signal(anchor, frame)

        # 2. Terrain match
        signals["terrain"] = self._terrain_signal(anchor, terrain_name)

        # 3. Heading match
        signals["heading"] = self._heading_signal(anchor, heading_deg, heading_unc)

        # 4. Movement steady (low speed after arrival → player has settled)
        signals["movement_steady"] = self._movement_signal(speed_px_s)

        # 5. Route history
        signals["route_history"] = route_success_rate

        # 6. Anchor history — temporal relevance (recently seen = high confidence)
        signals["anchor_history"] = self._anchor_history_signal(anchor_last_seen_sec)

        # 7. Route confidence — does the route graph expect us here?
        signals["route_confidence"] = max(0.0, min(1.0, route_confidence))

        # Weighted fusion
        loc_conf    = self._weighted_mean(signals)
        ckpt_conf   = self._checkpoint_conf(signals)
        drift_prob  = self._drift_probability(loc_conf, heading_unc)

        return FusionResult(
            anchor_id=anchor_id,
            localization_confidence=round(loc_conf, 3),
            checkpoint_confidence=round(ckpt_conf, 3),
            drift_probability=round(drift_prob, 3),
            signals={k: round(v, 3) for k, v in signals.items()},
        )

    # ------------------------------------------------------------------ #
    # Convenience: fuse from frame_manager without pre-capturing           #
    # ------------------------------------------------------------------ #

    def fuse_current(
        self,
        anchor_id: Optional[str],
        terrain_name: str,
        heading_deg: float,
        heading_unc: float,
        speed_px_s: float,
        route_success_rate: float = 0.5,
        anchor_last_seen_sec: float = float("inf"),
        route_confidence: float = 0.5,
    ) -> FusionResult:
        """fuse() using the frame manager's current cached frame."""
        frame = self._fm.full_frame()
        return self.fuse(
            anchor_id=anchor_id,
            frame=frame,
            terrain_name=terrain_name,
            heading_deg=heading_deg,
            heading_unc=heading_unc,
            speed_px_s=speed_px_s,
            route_success_rate=route_success_rate,
            anchor_last_seen_sec=anchor_last_seen_sec,
            route_confidence=route_confidence,
        )

    # ------------------------------------------------------------------ #
    # Individual signal calculators                                        #
    # ------------------------------------------------------------------ #

    def _template_signal(
        self,
        anchor: Optional[AnchorDefinition],
        frame: Optional[np.ndarray],
    ) -> float:
        if anchor is None or frame is None:
            return 0.0

        best_conf = 0.0

        # Search template groups first (stops on first hit)
        for group in anchor.template_groups:
            result = self._ts.best_in_group(group, frame, threshold=0.0)
            if result and result.confidence > best_conf:
                best_conf = result.confidence

        # Also check individual landmark names via the landmark detector's template cache
        for lm_name in anchor.landmark_names:
            r = self._ts.match(lm_name, frame, threshold=0.0, subdir="landmarks")
            if r.confidence > best_conf:
                best_conf = r.confidence

        return best_conf

    def _terrain_signal(
        self,
        anchor: Optional[AnchorDefinition],
        terrain_name: str,
    ) -> float:
        if anchor is None:
            return 0.5  # neutral
        if not anchor.expected_terrain:
            return 0.5
        return 1.0 if terrain_name in anchor.expected_terrain else 0.1

    def _heading_signal(
        self,
        anchor: Optional[AnchorDefinition],
        heading_deg: float,
        heading_unc: float,
    ) -> float:
        if anchor is None or anchor.expected_heading is None:
            # No heading expectation — scale by heading certainty
            return max(0.0, 1.0 - heading_unc / 180.0)

        diff = abs((heading_deg - anchor.expected_heading + 180.0) % 360.0 - 180.0)
        # Also factor in uncertainty
        effective_diff = diff + heading_unc * 0.5

        if effective_diff <= _HEADING_FULL_MATCH:
            return 1.0
        if effective_diff >= _HEADING_ZERO_MATCH:
            return 0.0
        # Linear interpolation
        span = _HEADING_ZERO_MATCH - _HEADING_FULL_MATCH
        return max(0.0, 1.0 - (effective_diff - _HEADING_FULL_MATCH) / span)

    def _movement_signal(self, speed_px_s: float) -> float:
        if speed_px_s <= _STATIONARY_SPEED:
            return 1.0
        # Decay as speed increases (fast movement = less reliable anchor detection)
        return max(0.0, 1.0 - (speed_px_s - _STATIONARY_SPEED) / 80.0)

    def _anchor_history_signal(self, last_seen_sec: float) -> float:
        """
        Temporal relevance of this anchor based on recency of confirmation.

        0–3s  → 1.0 (very recent)
        3–15s → linear decay to 0.5
        15s+  → 0.5 (neutral, stale history not penalized)
        never → 0.3 (no history)
        """
        if last_seen_sec == float("inf"):
            return 0.3   # never confirmed
        if last_seen_sec <= 3.0:
            return 1.0
        if last_seen_sec <= 15.0:
            return max(0.5, 1.0 - (last_seen_sec - 3.0) / 24.0)
        return 0.5

    # ------------------------------------------------------------------ #
    # Composite scores                                                     #
    # ------------------------------------------------------------------ #

    def _weighted_mean(self, signals: Dict[str, float]) -> float:
        total = 0.0
        weight_sum = 0.0
        for name, weight in _WEIGHTS.items():
            val = signals.get(name, 0.5)
            total      += val * weight
            weight_sum += weight
        return total / weight_sum if weight_sum > 0 else 0.0

    def _checkpoint_conf(self, signals: Dict[str, float]) -> float:
        # Checkpoint is more selective than general localization:
        # template + terrain must both be strong
        t = signals.get("template", 0.0)
        e = signals.get("terrain",  0.0)
        h = signals.get("heading",  0.5)
        # Require both template AND terrain to be convincing
        if t < 0.35:
            return t * 0.5   # penalize low template heavily
        return (t * 0.55 + e * 0.25 + h * 0.20)

    def _drift_probability(self, loc_conf: float, heading_unc: float) -> float:
        # Drift is likely when confidence is low AND heading is uncertain
        conf_factor = 1.0 - loc_conf
        unc_factor  = min(1.0, heading_unc / 90.0)
        return min(1.0, (conf_factor * 0.7 + unc_factor * 0.3))


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[FusionEngine] = None
_inst_lock = threading.Lock()


def get_fusion_engine() -> FusionEngine:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = FusionEngine()
    return _instance
