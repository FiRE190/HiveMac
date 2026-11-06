"""
LocalizationState — route-relative position belief for the navigation runtime.

This is NOT absolute coordinates.
This IS: "where the runtime believes it is, how confident it is, and how much
it has drifted from the last confirmed anchor."

The state is updated by three sources:
  - CheckpointValidator (anchor confirmed → confidence spike, drift reset)
  - FusionEngine       (per-tick signal fusion → gradual drift accumulation)
  - RecoveryManager    (recovery success → partial confidence restore)

Confidence thresholds:
  >= 0.80  HIGH    — traversal proceeds with standard margins
  0.50–0.80 MEDIUM — traversal proceeds; timeouts padded +30%
  0.25–0.50 LOW    — extra validation required; recovery recommended
  < 0.25   LOST   — traversal blocked; recovery required

Drift score [0, 1]:
  0.0 = freshly anchored
  → grows with dead-reckoning distance and heading uncertainty
  → reset to 0 on anchor confirmation
  1.0 = position completely unknown (forces LOST)

Public API:
    tracker = get_localization_tracker()
    tracker.confirm_anchor("hive_1_entrance", conf=0.92)
    tracker.accumulate_drift(distance_px=12.0, heading_uncertainty=5.0)
    state = tracker.state
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from utils.logger import get_logger

log = get_logger(__name__)


class PositionConfidence(Enum):
    HIGH   = auto()   # >= 0.80
    MEDIUM = auto()   # 0.50–0.80
    LOW    = auto()   # 0.25–0.50
    LOST   = auto()   # < 0.25


@dataclass
class LocalizationState:
    """Snapshot of the runtime's current position belief."""
    probable_anchor:        Optional[str]  = None
    confidence:             float          = 0.0
    last_confirmed_anchor:  Optional[str]  = None
    last_confirmation_time: float          = 0.0   # monotonic
    heading_confidence:     float          = 0.0
    drift_score:            float          = 0.0
    active_route:           Optional[str]  = None
    consecutive_failures:   int            = 0

    @property
    def tier(self) -> PositionConfidence:
        if self.confidence >= 0.80:
            return PositionConfidence.HIGH
        if self.confidence >= 0.50:
            return PositionConfidence.MEDIUM
        if self.confidence >= 0.25:
            return PositionConfidence.LOW
        return PositionConfidence.LOST

    @property
    def is_lost(self) -> bool:
        return self.tier == PositionConfidence.LOST

    @property
    def anchor_age(self) -> float:
        """Seconds since last anchor confirmation."""
        if self.last_confirmation_time == 0.0:
            return float("inf")
        return time.monotonic() - self.last_confirmation_time

    @property
    def timeout_multiplier(self) -> float:
        """Route timeout padding for this confidence tier."""
        return {
            PositionConfidence.HIGH:   1.0,
            PositionConfidence.MEDIUM: 1.3,
            PositionConfidence.LOW:    1.8,
            PositionConfidence.LOST:   2.5,
        }[self.tier]


# ── Tracker ────────────────────────────────────────────────────────────────────

# Drift accrual parameters
_DRIFT_PER_PX         = 0.0008   # drift added per pixel of dead-reckoning
_DRIFT_PER_DEG_UNC    = 0.004    # drift added per degree of heading uncertainty
_DRIFT_DECAY_PER_SEC  = 0.005    # passive decay when stationary
_CONFIDENCE_DECAY_AGE = 60.0     # seconds before confidence starts decaying passively
_FAILURE_CONFIDENCE_PENALTY = 0.12  # subtracted from confidence per consecutive failure


class LocalizationTracker:
    """
    Thread-safe tracker that maintains LocalizationState over a session.

    Call confirm_anchor() on every successful checkpoint validation.
    Call accumulate_drift() every movement tick with dead-reckoning data.
    Call record_failure() whenever a checkpoint validation fails.
    Call set_route() at the start of each go_to() call.
    """

    def __init__(self) -> None:
        self._lock  = threading.RLock()
        self._state = LocalizationState()

    @property
    def state(self) -> LocalizationState:
        with self._lock:
            import copy
            return copy.copy(self._state)

    @property
    def confidence(self) -> float:
        with self._lock:
            return self._state.confidence

    @property
    def is_lost(self) -> bool:
        with self._lock:
            return self._state.is_lost

    # ------------------------------------------------------------------ #
    # State updates                                                        #
    # ------------------------------------------------------------------ #

    def confirm_anchor(self, anchor_id: str, conf: float = 0.90) -> None:
        """
        Record a successful anchor confirmation.
        Spikes confidence, resets drift, clears failure count.
        """
        with self._lock:
            self._state.probable_anchor        = anchor_id
            self._state.confidence             = max(self._state.confidence, conf)
            self._state.last_confirmed_anchor  = anchor_id
            self._state.last_confirmation_time = time.monotonic()
            self._state.drift_score            = 0.0
            self._state.consecutive_failures   = 0
            log.debug("Localization: anchor confirmed '%s' conf=%.2f", anchor_id, conf)

    def soft_anchor(self, anchor_id: str, conf: float = 0.50) -> None:
        """
        Unconfirmed positional estimate (timeout arrival, no visual check).
        Updates probable_anchor but does NOT reset drift or failures.
        """
        with self._lock:
            self._state.probable_anchor = anchor_id
            # Use the lower of current confidence and the soft estimate
            self._state.confidence = min(self._state.confidence, conf) if self._state.confidence > 0 else conf
            log.debug("Localization: soft anchor '%s' conf=%.2f", anchor_id, conf)

    def accumulate_drift(self, distance_px: float, heading_uncertainty: float) -> None:
        """
        Accumulate dead-reckoning drift.
        distance_px: pixels traveled since last tick (from optical flow speed × elapsed)
        heading_uncertainty: current camera heading uncertainty in degrees
        """
        with self._lock:
            drift = (
                distance_px * _DRIFT_PER_PX
                + heading_uncertainty * _DRIFT_PER_DEG_UNC
            )
            self._state.drift_score = min(1.0, self._state.drift_score + drift)

            # Confidence also decays with drift
            conf_loss = drift * 0.5
            self._state.confidence = max(0.0, self._state.confidence - conf_loss)

            # Passive confidence decay by age
            age = self._state.anchor_age
            if age > _CONFIDENCE_DECAY_AGE:
                over = age - _CONFIDENCE_DECAY_AGE
                self._state.confidence = max(0.0, self._state.confidence - over * _DRIFT_DECAY_PER_SEC)

    def record_failure(self) -> None:
        """Record a checkpoint validation failure."""
        with self._lock:
            self._state.consecutive_failures += 1
            penalty = _FAILURE_CONFIDENCE_PENALTY * self._state.consecutive_failures
            self._state.confidence = max(0.0, self._state.confidence - penalty)
            log.debug("Localization: failure #%d conf now %.2f",
                      self._state.consecutive_failures, self._state.confidence)

    def set_route(self, destination: str) -> None:
        with self._lock:
            self._state.active_route = destination

    def set_heading_confidence(self, hc: float) -> None:
        with self._lock:
            self._state.heading_confidence = max(0.0, min(1.0, hc))

    def reset(self) -> None:
        """Full reset — call after respawn."""
        with self._lock:
            self._state = LocalizationState()

    def snap_to(self, anchor_id: str, confidence: float = 0.95) -> None:
        """Forced anchor snap (after respawn or manual confirmation)."""
        self.confirm_anchor(anchor_id, confidence)


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[LocalizationTracker] = None
_inst_lock = threading.Lock()


def get_localization_tracker() -> LocalizationTracker:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = LocalizationTracker()
    return _instance
