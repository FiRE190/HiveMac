"""
LocalizationEngine — probabilistic belief-state position manager.

Replaces the simplistic current_anchor/last_anchor model with a full
probabilistic anchor belief system:

  AnchorBelief per anchor:
    probability       — Bayesian posterior for "am I here?" [0, 1]
    confidence        — EMA-smoothed detector confidence
    last_seen         — monotonic timestamp of last observation
    persistence_sec   — seconds this anchor has been dominant
    consecutive_frames — frames above the entry threshold consecutively
    evidence_sources  — per-signal contributions from last fusion

  LocalizationEngineState:
    anchor_beliefs        — all tracked anchor beliefs
    dominant_anchor       — current highest-probability anchor
    dominant_confidence   — confidence of dominant anchor
    candidate_anchor      — anchor being evaluated for dominance (hysteresis)
    candidate_frames      — how many frames candidate has been above threshold
    drift_score           — accumulated dead-reckoning uncertainty [0, 1]
    heading_confidence    — camera heading reliability [0, 1]
    navigation_health     — overall nav health (computed externally) [0, 1]
    last_confirmed_anchor — last hard-confirmed anchor ID
    last_confirmation_time — monotonic time of last hard confirmation
    localization_stable   — True when dominant anchor is persistent and confident
    consecutive_failures  — validation failures since last confirmation
    active_route          — current navigation destination

Hysteresis (CRITICAL for eliminating flicker):
  - Entering dominance: requires confidence ≥ ENTER_THRESHOLD for
    MIN_PERSIST_FRAMES consecutive observation ticks
  - Leaving dominance: requires confidence < LEAVE_THRESHOLD

Confidence decay:
  - No observation for > DECAY_START_SEC → probability decays at DECAY_RATE/s
  - Recovers immediately when new evidence arrives

EMA smoothing (α = 0.35) prevents single-frame spikes from flipping state.
"""
from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from navigation.anchor_registry import get_anchor_registry
from utils.rolling_window import EMA
from utils.logger import get_logger

log = get_logger(__name__)

# ── Hysteresis thresholds ──────────────────────────────────────────────────────
_ENTER_THRESHOLD    = 0.78   # must sustain this to become dominant
_LEAVE_THRESHOLD    = 0.42   # must drop below this to lose dominance
_MIN_PERSIST_FRAMES = 3      # consecutive frames above _ENTER_THRESHOLD to enter

# ── Decay parameters ──────────────────────────────────────────────────────────
_DECAY_START_SEC  = 6.0    # grace period with no observation before decay
_DECAY_RATE       = 0.035  # probability subtracted per second during decay
_CONF_DECAY_RATE  = 0.025  # confidence decay per second (slower than probability)

# ── EMA smoothing ─────────────────────────────────────────────────────────────
_CONF_ALPHA = 0.35   # higher = faster response to new observations

# ── Failure penalties ─────────────────────────────────────────────────────────
_FAILURE_PENALTY = 0.10   # probability reduction per consecutive failure

# ── Drift parameters ──────────────────────────────────────────────────────────
_DRIFT_PER_PX      = 0.0008
_DRIFT_PER_DEG_UNC = 0.004
_DRIFT_PASSIVE_DECAY = 0.003  # drift reduction per second when stationary


@dataclass
class AnchorBelief:
    """Probabilistic belief about one anchor's current relevance."""
    anchor_id:          str
    probability:        float          # [0, 1] normalized posterior
    confidence:         float          # EMA-smoothed detector confidence
    last_seen:          float          # monotonic time of last observation
    persistence_sec:    float          # seconds continuously as dominant
    consecutive_frames: int            # frames above _ENTER_THRESHOLD
    evidence_sources:   Dict[str, float] = field(default_factory=dict)

    @property
    def age_sec(self) -> float:
        return time.monotonic() - self.last_seen

    @property
    def is_stale(self) -> bool:
        return self.age_sec > _DECAY_START_SEC


@dataclass
class LocalizationEngineState:
    """Complete snapshot of the localization belief state."""
    anchor_beliefs:          Dict[str, AnchorBelief] = field(default_factory=dict)
    dominant_anchor:         Optional[str]  = None
    dominant_confidence:     float          = 0.0
    candidate_anchor:        Optional[str]  = None
    candidate_frames:        int            = 0
    drift_score:             float          = 0.0
    heading_confidence:      float          = 0.0
    navigation_health:       float          = 1.0
    last_confirmed_anchor:   Optional[str]  = None
    last_confirmation_time:  float          = 0.0
    localization_stable:     bool           = False
    consecutive_failures:    int            = 0
    active_route:            Optional[str]  = None

    @property
    def anchor_age_sec(self) -> float:
        if self.last_confirmation_time == 0.0:
            return float("inf")
        return time.monotonic() - self.last_confirmation_time

    @property
    def is_lost(self) -> bool:
        return self.dominant_confidence < 0.25 or self.dominant_anchor is None

    @property
    def timeout_multiplier(self) -> float:
        c = self.dominant_confidence
        if c >= 0.80:
            return 1.0
        if c >= 0.50:
            return 1.3
        if c >= 0.25:
            return 1.8
        return 2.5


class LocalizationEngine:
    """
    Probabilistic anchor belief-state manager.

    Thread-safe (RLock on all state mutations).
    Call update_from_fusion() after every CheckpointValidator run.
    Call accumulate_drift() every movement tick.
    Call confirm_anchor() after temporal validation passes.
    """

    def __init__(self) -> None:
        self._lock     = threading.RLock()
        self._registry = get_anchor_registry()
        self._state    = LocalizationEngineState()
        self._beliefs: Dict[str, AnchorBelief] = {}
        self._last_decay_tick = time.monotonic()

    # ------------------------------------------------------------------ #
    # Primary update                                                      #
    # ------------------------------------------------------------------ #

    def update_from_fusion(
        self,
        anchor_id: str,
        fusion_confidence: float,
        signals: Dict[str, float],
        heading_confidence: float = 0.5,
    ) -> None:
        """
        Update belief state from a FusionEngine result.

        Called after each CheckpointValidator run (during VALIDATING state).
        Updates EMA confidence, recalculates hysteresis, re-evaluates dominant.
        """
        with self._lock:
            now = time.monotonic()

            # Get or create belief for this anchor
            if anchor_id not in self._beliefs:
                # Seed EMA directly from first observation (not from zero).
                # Starting from zero would take many frames to cross the entry
                # threshold, defeating the purpose of hysteresis.
                self._beliefs[anchor_id] = AnchorBelief(
                    anchor_id=anchor_id,
                    probability=fusion_confidence * 0.7,
                    confidence=fusion_confidence,
                    last_seen=now,
                    persistence_sec=0.0,
                    consecutive_frames=0,
                    evidence_sources={},
                )
                # Attach a shared EMA tracker (stored in evidence_sources for now;
                # future refactor can add it as a proper field)
                self._beliefs[anchor_id].evidence_sources["_ema_obj"] = EMA(
                    alpha=_CONF_ALPHA, initial=fusion_confidence
                )
            else:
                belief = self._beliefs[anchor_id]
                # Use shared EMA utility for confidence smoothing
                ema: EMA = belief.evidence_sources.get("_ema_obj") or EMA(
                    alpha=_CONF_ALPHA, initial=belief.confidence
                )
                belief.confidence = ema.update(fusion_confidence)
                belief.evidence_sources["_ema_obj"] = ema

            belief = self._beliefs[anchor_id]
            belief.last_seen        = now
            belief.evidence_sources = signals

            # Hysteresis: track frames above entry threshold
            if belief.confidence >= _ENTER_THRESHOLD:
                belief.consecutive_frames += 1
            else:
                belief.consecutive_frames = max(0, belief.consecutive_frames - 1)

            # Update heading confidence
            self._state.heading_confidence = heading_confidence

            # Run decay on all stale beliefs
            self._apply_decay(now)

            # Re-evaluate dominant anchor
            self._update_dominant(now)

    def confirm_anchor(self, anchor_id: str, conf: float = 0.90) -> None:
        """
        Hard confirmation — spike belief, reset drift and failures.
        Call after temporal validation passes.
        """
        with self._lock:
            now = time.monotonic()

            if anchor_id not in self._beliefs:
                self._beliefs[anchor_id] = AnchorBelief(
                    anchor_id=anchor_id,
                    probability=conf,
                    confidence=conf,
                    last_seen=now,
                    persistence_sec=0.0,
                    consecutive_frames=_MIN_PERSIST_FRAMES,  # force entry
                    evidence_sources={"confirmed": conf},
                )
            else:
                b = self._beliefs[anchor_id]
                b.confidence        = max(b.confidence, conf)
                b.probability       = max(b.probability, conf)
                b.last_seen         = now
                b.consecutive_frames = max(b.consecutive_frames, _MIN_PERSIST_FRAMES)

            # Force dominance (hard confirmation bypasses hysteresis)
            self._state.dominant_anchor        = anchor_id
            self._state.dominant_confidence    = conf
            self._state.last_confirmed_anchor  = anchor_id
            self._state.last_confirmation_time = now
            self._state.drift_score            = 0.0
            self._state.consecutive_failures   = 0
            self._state.localization_stable    = True
            self._state.candidate_anchor       = None
            self._state.candidate_frames       = 0

            log.debug("LocalizationEngine: confirmed '%s' conf=%.2f", anchor_id, conf)

    def soft_anchor(self, anchor_id: str, conf: float = 0.50) -> None:
        """
        Unconfirmed positional estimate. Updates belief but does NOT
        reset drift or failures — use when timing suggests we arrived
        but validation didn't confirm it.
        """
        with self._lock:
            now = time.monotonic()
            existing_conf = 0.0
            if anchor_id in self._beliefs:
                existing_conf = self._beliefs[anchor_id].confidence

            # Take the lower of current and soft estimate — pessimistic
            new_conf = min(existing_conf, conf) if existing_conf > 0 else conf

            self.update_from_fusion(
                anchor_id=anchor_id,
                fusion_confidence=new_conf,
                signals={"soft": new_conf},
                heading_confidence=self._state.heading_confidence,
            )

            if self._state.dominant_anchor is None:
                self._state.dominant_anchor     = anchor_id
                self._state.dominant_confidence = new_conf

    def accumulate_drift(self, distance_px: float, heading_uncertainty: float) -> None:
        """Accumulate dead-reckoning drift during movement."""
        with self._lock:
            drift = (
                distance_px * _DRIFT_PER_PX +
                heading_uncertainty * _DRIFT_PER_DEG_UNC
            )
            self._state.drift_score = min(1.0, self._state.drift_score + drift)

            # Confidence of dominant anchor also erodes with drift
            if self._state.dominant_anchor and self._state.dominant_anchor in self._beliefs:
                b = self._beliefs[self._state.dominant_anchor]
                b.confidence   = max(0.0, b.confidence - drift * 0.4)
                b.probability  = max(0.0, b.probability - drift * 0.3)
                self._state.dominant_confidence = b.confidence

    def decay_passive(self, elapsed_sec: float) -> None:
        """
        Passive decay when stationary without new observations.
        Call periodically from the navigation loop (e.g. every 2s).
        """
        with self._lock:
            if self._state.drift_score > 0:
                self._state.drift_score = max(
                    0.0,
                    self._state.drift_score - _DRIFT_PASSIVE_DECAY * elapsed_sec,
                )

    def record_failure(self) -> None:
        """Record a validation failure — penalizes dominant belief."""
        with self._lock:
            self._state.consecutive_failures += 1
            penalty = _FAILURE_PENALTY * self._state.consecutive_failures
            dom = self._state.dominant_anchor
            if dom and dom in self._beliefs:
                b = self._beliefs[dom]
                b.confidence  = max(0.0, b.confidence - penalty)
                b.probability = max(0.0, b.probability - penalty)
                self._state.dominant_confidence = b.confidence

    def set_route(self, destination: str) -> None:
        with self._lock:
            self._state.active_route = destination

    def set_navigation_health(self, health: float) -> None:
        with self._lock:
            self._state.navigation_health = max(0.0, min(1.0, health))

    def reset(self) -> None:
        """Full reset — call after respawn."""
        with self._lock:
            self._beliefs = {}
            self._state   = LocalizationEngineState()

    def snap_to(self, anchor_id: str, confidence: float = 0.95) -> None:
        """Forced anchor snap (after respawn or manual confirmation)."""
        self.confirm_anchor(anchor_id, confidence)

    # ------------------------------------------------------------------ #
    # State queries                                                       #
    # ------------------------------------------------------------------ #

    @property
    def state(self) -> LocalizationEngineState:
        with self._lock:
            s = copy.copy(self._state)
            s.anchor_beliefs = {k: copy.copy(v) for k, v in self._beliefs.items()}
            return s

    @property
    def dominant_anchor(self) -> Optional[str]:
        with self._lock:
            return self._state.dominant_anchor

    @property
    def dominant_confidence(self) -> float:
        with self._lock:
            return self._state.dominant_confidence

    @property
    def is_lost(self) -> bool:
        with self._lock:
            return self._state.is_lost

    @property
    def drift_score(self) -> float:
        with self._lock:
            return self._state.drift_score

    @property
    def localization_stable(self) -> bool:
        with self._lock:
            return self._state.localization_stable

    def belief_for(self, anchor_id: str) -> Optional[AnchorBelief]:
        with self._lock:
            b = self._beliefs.get(anchor_id)
            return copy.copy(b) if b else None

    # Backward-compat property for code that reads .current_node
    @property
    def current_node(self) -> Optional[str]:
        return self.dominant_anchor

    def confidence(self) -> float:
        return self.dominant_confidence

    def observe(self, reading) -> None:
        """Legacy compatibility: accept a LandmarkReading."""
        if hasattr(reading, "confidence") and hasattr(reading, "name"):
            self.update_from_fusion(
                anchor_id=reading.name,
                fusion_confidence=reading.confidence,
                signals={"landmark": reading.confidence},
            )

    # ------------------------------------------------------------------ #
    # Internal                                                            #
    # ------------------------------------------------------------------ #

    def _apply_decay(self, now: float) -> None:
        """Decay stale beliefs. Called inside the lock."""
        for anchor_id, belief in list(self._beliefs.items()):
            age = now - belief.last_seen
            if age > _DECAY_START_SEC:
                excess = age - _DECAY_START_SEC
                decay  = _DECAY_RATE * excess * 0.016  # per-tick (assume ~16ms tick)
                belief.probability = max(0.0, belief.probability - decay)
                belief.confidence  = max(0.0, belief.confidence  - _CONF_DECAY_RATE * decay)

    def _update_dominant(self, now: float) -> None:
        """Re-evaluate the dominant anchor with hysteresis. Called inside the lock."""
        if not self._beliefs:
            return

        current_dom = self._state.dominant_anchor
        current_dom_belief = self._beliefs.get(current_dom) if current_dom else None

        # Find the highest-confidence belief
        best_id   = max(self._beliefs, key=lambda k: self._beliefs[k].confidence)
        best      = self._beliefs[best_id]

        if current_dom is None:
            # No dominant yet — enter immediately if above threshold
            if best.consecutive_frames >= _MIN_PERSIST_FRAMES:
                self._state.dominant_anchor     = best_id
                self._state.dominant_confidence = best.confidence
                self._state.localization_stable = True
                best.persistence_sec = 0.0
            return

        if current_dom_belief is not None:
            # Update persistence if currently dominant and above threshold
            if current_dom_belief.confidence >= _ENTER_THRESHOLD:
                current_dom_belief.persistence_sec += 0.045  # approx tick interval
                self._state.localization_stable = (
                    current_dom_belief.persistence_sec >= 0.5
                )

        # Check if dominant should be vacated
        dom_dropping = (
            current_dom_belief is None or
            current_dom_belief.confidence < _LEAVE_THRESHOLD
        )

        # Check if a new candidate is ready to take over
        if best_id != current_dom and best.consecutive_frames >= _MIN_PERSIST_FRAMES:
            if dom_dropping or best.confidence > (self._state.dominant_confidence + 0.20):
                # Hysteresis transition
                log.debug(
                    "LocalizationEngine: anchor transition '%s'→'%s' "
                    "(old_conf=%.2f new_conf=%.2f)",
                    current_dom, best_id,
                    self._state.dominant_confidence, best.confidence,
                )
                if current_dom_belief:
                    current_dom_belief.persistence_sec = 0.0
                self._state.dominant_anchor     = best_id
                self._state.dominant_confidence = best.confidence
                self._state.localization_stable = False  # reset until persistent
                best.persistence_sec = 0.0
                self._state.candidate_anchor = None
                self._state.candidate_frames = 0
                return

        # Track candidate (not yet ready for transition)
        if best_id != current_dom and best.confidence >= _ENTER_THRESHOLD:
            if self._state.candidate_anchor == best_id:
                self._state.candidate_frames += 1
            else:
                self._state.candidate_anchor = best_id
                self._state.candidate_frames = 1
        else:
            self._state.candidate_anchor = None
            self._state.candidate_frames = 0

        # Update dominant confidence from current dominant belief
        if current_dom_belief:
            self._state.dominant_confidence = current_dom_belief.confidence


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[LocalizationEngine] = None
_inst_lock = threading.Lock()


def get_localization_engine() -> LocalizationEngine:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = LocalizationEngine()
    return _instance
