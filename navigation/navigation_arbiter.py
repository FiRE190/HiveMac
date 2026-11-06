"""
NavigationArbiter — single decision authority for the navigation runtime.

PROBLEM SOLVED:
  Without a central arbiter, four subsystems can produce incompatible truths
  simultaneously:
    - LocalizationEngine: "I'm at hive_1_entrance with 0.82 confidence"
    - TemporalValidator:  "confirmation failed (rolling_conf=0.45)"
    - NavigationHealth:   "health=0.51 → WARNING, consider recovery"
    - EdgeCalibration:    "edge reliability=0.35 → unreliable"

  No individual module has the authority to resolve which signal wins.
  Result: oscillation, contradictory recovery triggers, wasted cycles.

SOLUTION — explicit per-decision authority:

  ┌─────────────────────────────────────────────────────────────────┐
  │  Decision            │ Authority                                 │
  ├─────────────────────────────────────────────────────────────────┤
  │  Localization truth  │ LocalizationEngine ONLY                  │
  │  Transition validity │ TemporalValidator ONLY                    │
  │  Movement timing     │ EdgeCalibration ONLY                     │
  │  State progression   │ RouteFSM ONLY                            │
  │  Recovery ordering   │ RecoveryArbiter ONLY                     │
  │  CONFLICT RESOLUTION │ NavigationArbiter (this module)          │
  └─────────────────────────────────────────────────────────────────┘

  No module may override another module's decision output directly.
  When signals conflict, they are routed HERE for resolution.

Decision precedence rules (applied in order):

  R1  RecoveryArbiter.is_active → PAUSE (never stack recovery)
  R2  Health.should_preempt AND NOT temporal_confirmed AND NOT recovery_active
       → SOFT_RECOVER/HARD_RECOVER (engine-dependent)
       Health preempt is suppressed when temporal validation confirmed arrival
       — confirmed edges must PROCEED; health catches up before the next edge.
  R3  TemporalValidator confirmed AND engine.localization_stable → PROCEED
  R4  TemporalValidator confirmed AND NOT engine.localization_stable
       → VALIDATE_MORE (2 additional frames; hysteresis not stable yet)
  R5  TemporalValidator marginal AND engine.localization_stable → PROCEED
       (use hysteresis stability as tiebreaker for marginal detections)
  R6  TemporalValidator marginal AND NOT engine.localization_stable
       → VALIDATE_MORE
  R7  edge_reliability < UNRELIABLE_THRESHOLD (0.40) → HARD_RECOVER
       (planner already penalized this edge; FSM should not attempt it)
  R8  Health.is_warning → SOFT_RECOVER
  R9  Default → SOFT_RECOVER (validation failed, conservative)

Public API:
    arb = get_navigation_arbiter()
    decision = arb.decide(ArbiterContext(...))
    if decision.action == NavigationAction.PROCEED:
        localization_engine.confirm_anchor(anchor_id, decision.confidence_floor)
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from planning.recovery_manager import RecoveryLevel
from utils.logger import get_logger

log = get_logger(__name__)

# Canonical edge reliability thresholds — imported by RouteFSM so both systems
# use identical values. Changing them here propagates everywhere automatically.
EDGE_UNRELIABLE_THRESHOLD = 0.40   # below this → HARD_RECOVER before traversal
EDGE_MARGINAL_THRESHOLD   = 0.70   # below this → extra validation frames

# Module-private aliases used by the R-rules below
_UNRELIABLE_THRESHOLD = EDGE_UNRELIABLE_THRESHOLD
_MARGINAL_THRESHOLD   = EDGE_MARGINAL_THRESHOLD


class NavigationAction(Enum):
    PROCEED       = "proceed"         # temporal confirmed + engine agrees → go
    VALIDATE_MORE = "validate_more"   # gather N more frames before deciding
    SOFT_RECOVER  = "soft_recover"    # MICRO_CORRECTION or HEADING_REALIGN
    HARD_RECOVER  = "hard_recover"    # CHECKPOINT_ROLLBACK through FULL_RESET
    PAUSE         = "pause"           # recovery already active — do nothing


@dataclass
class ArbiterContext:
    """All inputs required for one arbitration decision."""
    # From TemporalValidator
    temporal_confirmed: bool
    temporal_marginal:  bool
    temporal_confidence: float
    temporal_frame_count: int

    # From LocalizationEngine
    localization_stable: bool
    dominant_confidence: float

    # From NavigationHealth
    health_should_preempt: bool
    health_is_warning:     bool
    health_overall:        float

    # From EdgeCalibration
    edge_reliability: float
    edge_key:         str

    # From RecoveryArbiter
    recovery_active:  bool


@dataclass
class NavigationDecision:
    """
    The arbiter's verdict for one validation/transition decision.

    action:                    what to do next
    recovery_from_level:       starting level if action is *_RECOVER
    extra_validation_frames:   additional frames to gather if VALIDATE_MORE
    confidence_floor:          minimum confidence to accept for PROCEED
    rationale:                 human-readable rule that fired
    """
    action:                  NavigationAction
    recovery_from_level:     Optional[RecoveryLevel] = None
    extra_validation_frames: int   = 0
    confidence_floor:        float = 0.55
    rationale:               str   = ""

    @property
    def should_recover(self) -> bool:
        return self.action in (NavigationAction.SOFT_RECOVER, NavigationAction.HARD_RECOVER)

    @property
    def should_proceed(self) -> bool:
        return self.action == NavigationAction.PROCEED


class NavigationArbiter:
    """
    Central conflict resolution for navigation decisions.

    Stateless — all state comes via ArbiterContext.
    Thread-safe (no internal mutable state).
    __slots__ = () enforces zero-state: any accidental self.x = ... will
    raise AttributeError at the point of assignment, not silently corrupt
    arbitration behaviour during a long run.
    """

    __slots__ = ()

    # ------------------------------------------------------------------ #
    # Primary decision entry point                                        #
    # ------------------------------------------------------------------ #

    def decide(self, ctx: ArbiterContext) -> NavigationDecision:
        """
        Apply precedence rules and return a single NavigationDecision.
        Called by Navigator after TemporalValidator completes.
        """
        # R1 — never stack recovery
        if ctx.recovery_active:
            return NavigationDecision(
                action=NavigationAction.PAUSE,
                rationale="R1: recovery already active via RecoveryArbiter",
            )

        # R2 — health preempt — only when temporal validation did NOT confirm arrival.
        #
        # Why: the arbiter is called after FSM completes. If temporal validation just
        # confirmed the destination (temporal_confirmed=True), the edge succeeded and we
        # must PROCEED to let the Navigator register the arrival. Health concerns are
        # caught by the proactive check BEFORE the next edge — not after this one.
        #
        # Firing R2 on a confirmed edge would silently discard a valid arrival, forcing
        # an unnecessary recovery that leaves the route half-executed.
        if ctx.health_should_preempt and not ctx.temporal_confirmed:
            if ctx.localization_stable:
                return NavigationDecision(
                    action=NavigationAction.SOFT_RECOVER,
                    recovery_from_level=RecoveryLevel.HEADING_REALIGN,
                    rationale=f"R2: health preempt (health={ctx.health_overall:.2f}), no confirmation, engine stable",
                )
            else:
                return NavigationDecision(
                    action=NavigationAction.HARD_RECOVER,
                    recovery_from_level=RecoveryLevel.CHECKPOINT_ROLLBACK,
                    rationale=f"R2h: health preempt (health={ctx.health_overall:.2f}), no confirmation, engine unstable",
                )

        # R3 — confirmed + stable → PROCEED
        if ctx.temporal_confirmed and ctx.localization_stable:
            return NavigationDecision(
                action=NavigationAction.PROCEED,
                confidence_floor=ctx.temporal_confidence,
                rationale="R3: temporal confirmed + engine stable",
            )

        # R4 — confirmed but engine not yet stable → gather more evidence
        if ctx.temporal_confirmed and not ctx.localization_stable:
            return NavigationDecision(
                action=NavigationAction.VALIDATE_MORE,
                extra_validation_frames=2,
                rationale="R4: temporal confirmed but engine hysteresis not stable",
            )

        # R5 — marginal detection, but engine hysteresis is stable
        #      (hysteresis provides the missing certainty)
        if ctx.temporal_marginal and ctx.localization_stable:
            return NavigationDecision(
                action=NavigationAction.PROCEED,
                confidence_floor=ctx.temporal_confidence * 0.85,
                rationale="R5: marginal detection + engine hysteresis stable → tiebreak",
            )

        # R6 — marginal but engine not stable → need more frames
        if ctx.temporal_marginal and not ctx.localization_stable:
            return NavigationDecision(
                action=NavigationAction.VALIDATE_MORE,
                extra_validation_frames=3,
                rationale="R6: marginal + engine unstable → gather more frames",
            )

        # R7 — unreliable edge → hard recover before attempting traversal
        if ctx.edge_reliability < _UNRELIABLE_THRESHOLD:
            return NavigationDecision(
                action=NavigationAction.HARD_RECOVER,
                recovery_from_level=RecoveryLevel.CHECKPOINT_ROLLBACK,
                rationale=f"R7: edge '{ctx.edge_key}' reliability={ctx.edge_reliability:.2f} < {_UNRELIABLE_THRESHOLD}",
            )

        # R8 — health warning → soft recover
        if ctx.health_is_warning:
            return NavigationDecision(
                action=NavigationAction.SOFT_RECOVER,
                recovery_from_level=RecoveryLevel.MICRO_CORRECTION,
                rationale=f"R8: health warning (health={ctx.health_overall:.2f})",
            )

        # R9 — default: validation failed, conservative soft recover
        return NavigationDecision(
            action=NavigationAction.SOFT_RECOVER,
            recovery_from_level=RecoveryLevel.MICRO_CORRECTION,
            rationale="R9: default — temporal validation failed",
        )

    # ------------------------------------------------------------------ #
    # Pre-edge evaluation (before traversal starts)                       #
    # ------------------------------------------------------------------ #

    def decide_pre_edge(
        self,
        edge_key: str,
        edge_reliability: float,
        health_should_preempt: bool,
        health_overall: float,
        recovery_active: bool,
    ) -> NavigationDecision:
        """
        Decide whether to proceed with edge traversal or recover first.

        Called in RouteFSM.PREPARING before any movement begins.
        Enforces: planner and executor must agree on edge viability.
        """
        if recovery_active:
            return NavigationDecision(
                action=NavigationAction.PAUSE,
                rationale="pre-edge R1: recovery already active",
            )

        if health_should_preempt:
            return NavigationDecision(
                action=NavigationAction.SOFT_RECOVER,
                recovery_from_level=RecoveryLevel.HEADING_REALIGN,
                rationale=f"pre-edge R2: health preempt (health={health_overall:.2f})",
            )

        if edge_reliability < _UNRELIABLE_THRESHOLD:
            return NavigationDecision(
                action=NavigationAction.HARD_RECOVER,
                recovery_from_level=RecoveryLevel.CHECKPOINT_ROLLBACK,
                rationale=f"pre-edge R7: edge unreliable ({edge_reliability:.2f})",
            )

        return NavigationDecision(
            action=NavigationAction.PROCEED,
            confidence_floor=0.55,
            rationale="pre-edge: proceed",
        )


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[NavigationArbiter] = None
_inst_lock = threading.Lock()


def get_navigation_arbiter() -> NavigationArbiter:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = NavigationArbiter()
    return _instance
