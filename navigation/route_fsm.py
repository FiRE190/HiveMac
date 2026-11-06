"""
RouteFSM — explicit state machine for single-edge traversal execution.

Replaces the ad-hoc sequential execution logic in navigator._execute_plan()
with a formal, observable, telemetry-emitting FSM.

States:
  IDLE              → initial state before run() is called
  PREPARING         → gather terrain, assess camera state needs
  NORMALIZING_CAMERA → F-reset camera heading
  ALIGNING_HEADING  → align camera to edge's expected heading
  TRAVERSING        → MovementExecutor executing the edge
  VALIDATING        → TemporalValidator accumulating evidence
  CONFIRMED         → temporal validation passed → terminal success
  RECOVERING        → RecoveryManager running
  FAILED            → terminal failure (stop_event or unrecoverable)

State transitions are logged and exposed via telemetry so the
NavigationDebugger can observe each edge's execution in real time.

Key design decisions:
  - NORMALIZING_CAMERA failure is NOT fatal: proceed to TRAVERSING anyway.
    Camera uncertainty is tracked by LocalizationEngine and affects confidence.
  - ALIGNING_HEADING failure is NOT fatal: same reasoning.
  - Only TRAVERSING→FAILED (stop_event) and RECOVERING→FAILED (all levels
    exhausted) are terminal failures.
  - The FSM signals needs_replan=True when recovery succeeds but the route
    must be replanned from the new anchor.

Public API:
    fsm = RouteFSM(edge, terrain_fn, stop_event)
    result = fsm.run()
    if result.final_state == RouteFSMState.CONFIRMED:
        localization_engine.confirm_anchor(edge.to_node, result.confidence)
"""
from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, List, Optional

from navigation.types import NavEdge, EdgeStatus
from navigation.movement_executor import get_movement_executor
from navigation.camera_state import get_camera_state_manager
from navigation.anchor_registry import get_anchor_registry
from navigation.edge_calibration import get_edge_calibration
from navigation.recovery_arbiter import get_recovery_arbiter
from navigation.navigation_arbiter import EDGE_UNRELIABLE_THRESHOLD, EDGE_MARGINAL_THRESHOLD
from navigation.temporal_validator import TemporalValidator
from planning.recovery_manager import get_recovery_manager, RecoveryLevel, RecoveryResult
from utils.logger import get_logger

log = get_logger(__name__)


class RouteFSMState(Enum):
    IDLE               = "idle"
    PREPARING          = "preparing"
    NORMALIZING_CAMERA = "normalizing_camera"
    ALIGNING_HEADING   = "aligning_heading"
    TRAVERSING         = "traversing"
    VALIDATING         = "validating"
    CONFIRMED          = "confirmed"
    RECOVERING         = "recovering"
    FAILED             = "failed"


@dataclass
class FSMTelemetry:
    """Live telemetry snapshot for this FSM run."""
    edge_key:          str
    state:             str
    elapsed_sec:       float
    confidence:        float
    validation_frames: int
    recovery_level:    Optional[str]
    state_history:     List[str]
    timing:            Dict[str, float] = field(default_factory=dict)


@dataclass
class FSMResult:
    """Final outcome of one RouteFSM.run() call."""
    final_state:        RouteFSMState
    confirmed_anchor:   Optional[str]
    confidence:         float
    elapsed_sec:        float
    recovery_level:     Optional[RecoveryLevel] = None
    needs_replan:       bool = False
    drifted:            bool = False
    telemetry:          Optional[FSMTelemetry] = None
    # Raw temporal validation outcome — consumed by NavigationArbiter in Navigator
    temporal_confirmed: bool = False
    temporal_marginal:  bool = False
    temporal_frames:    int  = 0

    def __post_init__(self) -> None:
        # Mutual exclusivity: TemporalValidator emits exactly one of
        # {confirmed, marginal, neither}. Both True would mean two
        # conflicting validators agreed AND disagreed simultaneously.
        if self.temporal_confirmed and self.temporal_marginal:
            raise ValueError(
                f"FSMResult invariant violated: temporal_confirmed and temporal_marginal "
                f"cannot both be True (edge→{self.confirmed_anchor}, "
                f"frames={self.temporal_frames}, conf={self.confidence:.3f})"
            )
        # A confirmed result with zero frames means validation was never run —
        # the caller set temporal_confirmed=True without accumulating evidence.
        if self.temporal_confirmed and self.temporal_frames == 0:
            raise ValueError(
                f"FSMResult invariant violated: temporal_confirmed=True but "
                f"temporal_frames=0 (edge→{self.confirmed_anchor})"
            )


class RouteFSM:
    """
    Explicit state machine for one NavEdge traversal.

    Dependencies are resolved via singletons; no state is mutated
    outside the LocalizationEngine (which is updated by the caller
    after FSMResult is returned).
    """

    def __init__(
        self,
        edge: NavEdge,
        terrain_fn: Callable[[], str],
        stop_event: threading.Event,
    ) -> None:
        self._edge       = edge
        self._terrain_fn = terrain_fn
        self._stop       = stop_event
        self._state      = RouteFSMState.IDLE
        self._state_hist: List[str] = []
        self._timing:     Dict[str, float] = {}
        self._executor   = get_movement_executor()
        self._csm        = get_camera_state_manager()
        self._registry   = get_anchor_registry()
        self._recovery   = get_recovery_manager()

        self._edge_key   = f"{edge.from_node}→{edge.to_node}"
        self._t0         = 0.0

        # Accumulated per-state outputs
        self._confidence          = 0.0
        self._val_frames          = 0
        self._drifted             = False
        self._recovery_lvl: Optional[RecoveryLevel] = None
        self._temporal_confirmed  = False
        self._temporal_marginal   = False
        # Set in PREPARING based on edge reliability; consumed by VALIDATING
        self._required_validation_frames: int = 3

        self._rec_arbiter = get_recovery_arbiter()

    # ------------------------------------------------------------------ #
    # Main entry point                                                    #
    # ------------------------------------------------------------------ #

    def run(self) -> FSMResult:
        """Execute the full FSM. Returns when terminal state is reached."""
        self._t0 = time.monotonic()
        self._transition(RouteFSMState.PREPARING)

        while self._state not in (
            RouteFSMState.CONFIRMED,
            RouteFSMState.FAILED,
        ):
            if self._stop.is_set():
                return self._result(RouteFSMState.FAILED)

            if self._state == RouteFSMState.PREPARING:
                self._run_preparing()
            elif self._state == RouteFSMState.NORMALIZING_CAMERA:
                self._run_normalizing()
            elif self._state == RouteFSMState.ALIGNING_HEADING:
                self._run_aligning()
            elif self._state == RouteFSMState.TRAVERSING:
                self._run_traversing()
            elif self._state == RouteFSMState.VALIDATING:
                self._run_validating()
            elif self._state == RouteFSMState.RECOVERING:
                self._run_recovering()
                break  # recovering always returns to caller

        return self._result(self._state)

    # ------------------------------------------------------------------ #
    # State handlers                                                      #
    # ------------------------------------------------------------------ #

    def _run_preparing(self) -> None:
        """Determine which pre-traversal steps are needed."""
        t = time.monotonic()

        if self._stop.is_set():
            self._transition(RouteFSMState.FAILED)
            return

        # EdgeCalibration authority: check reliability before committing to traversal.
        # RecoveryArbiter is consulted by NavigationArbiter, not here — FSM only
        # decides whether this edge should be attempted at all.
        calibration = get_edge_calibration()
        reliability = calibration.edge_score(self._edge_key)

        if reliability < EDGE_UNRELIABLE_THRESHOLD:
            # Unreliable edge — pre-emptive recovery before any movement
            log.warning(
                "RouteFSM[%s]: edge reliability=%.2f < UNRELIABLE(%.2f) — recovering before traversal",
                self._edge_key, reliability, EDGE_UNRELIABLE_THRESHOLD,
            )
            self._transition(RouteFSMState.RECOVERING)
            return

        if reliability < EDGE_MARGINAL_THRESHOLD:
            # Marginal edge — require more validation frames to confirm arrival
            self._required_validation_frames = 5
            log.debug(
                "RouteFSM[%s]: edge reliability=%.2f < MARGINAL(%.2f) — using %d validation frames",
                self._edge_key, reliability, EDGE_MARGINAL_THRESHOLD, self._required_validation_frames,
            )

        anchor = self._registry.get(self._edge.to_node)

        needs_norm = not self._csm.is_traversal_ready
        needs_align = (
            anchor is not None and
            anchor.expected_heading is not None and
            abs(self._csm.heading - anchor.expected_heading) > anchor.heading_tolerance
        )

        self._timing["prepare_sec"] = time.monotonic() - t

        if needs_norm:
            self._transition(RouteFSMState.NORMALIZING_CAMERA)
        elif needs_align:
            self._transition(RouteFSMState.ALIGNING_HEADING)
        else:
            self._transition(RouteFSMState.TRAVERSING)

    def _run_normalizing(self) -> None:
        """F-reset camera. Failure is tolerated — reduces confidence only."""
        t = time.monotonic()
        ok = self._csm.ensure_traversal_state(self._stop)
        self._timing["normalize_sec"] = time.monotonic() - t

        if self._stop.is_set():
            self._transition(RouteFSMState.FAILED)
            return

        anchor = self._registry.get(self._edge.to_node)
        needs_align = (
            ok and
            anchor is not None and
            anchor.expected_heading is not None and
            abs(self._csm.heading - anchor.expected_heading) > anchor.heading_tolerance
        )

        if needs_align:
            self._transition(RouteFSMState.ALIGNING_HEADING)
        else:
            self._transition(RouteFSMState.TRAVERSING)

    def _run_aligning(self) -> None:
        """Align camera to expected heading. Best-effort — not fatal if fails."""
        t = time.monotonic()
        self._csm.align_for_anchor(self._edge.to_node, self._stop)
        self._timing["align_sec"] = time.monotonic() - t

        if self._stop.is_set():
            self._transition(RouteFSMState.FAILED)
            return

        self._transition(RouteFSMState.TRAVERSING)

    def _run_traversing(self) -> None:
        """Execute movement. Handles stall/stuck internally in executor."""
        t = time.monotonic()

        if self._stop.is_set():
            self._transition(RouteFSMState.FAILED)
            return

        try:
            result = self._executor.execute(self._edge, self._stop)
        except Exception as exc:
            log.error("RouteFSM[%s]: executor raised: %s", self._edge_key, exc)
            self._transition(RouteFSMState.FAILED)
            return

        self._timing["traverse_sec"] = time.monotonic() - t

        if result.status == EdgeStatus.FAILED or self._stop.is_set():
            self._transition(RouteFSMState.FAILED)
        else:
            self._transition(RouteFSMState.VALIDATING)

    def _run_validating(self) -> None:
        """Accumulate temporal evidence before confirming arrival."""
        t = time.monotonic()

        terrain_name = self._terrain_fn()
        tv = TemporalValidator(
            anchor_id=self._edge.to_node,
            min_frames=self._required_validation_frames,
        )

        val_result = tv.accumulate(
            terrain_name=terrain_name,
            heading_deg=self._csm.heading,
            heading_unc=self._csm.heading_uncertainty,
            stop_event=self._stop,
        )

        self._timing["validate_sec"] = time.monotonic() - t
        self._val_frames         = val_result.frame_count
        self._drifted            = val_result.drift_detected
        self._confidence         = val_result.rolling_confidence
        self._temporal_confirmed = val_result.confirmed
        self._temporal_marginal  = val_result.marginal

        if self._stop.is_set():
            self._transition(RouteFSMState.FAILED)
        elif val_result.confirmed:
            self._transition(RouteFSMState.CONFIRMED)
        elif val_result.marginal:
            self._confidence = val_result.rolling_confidence * 0.80
            self._transition(RouteFSMState.CONFIRMED)
        else:
            self._transition(RouteFSMState.RECOVERING)

    def _run_recovering(self) -> None:
        """Delegate to RecoveryManager under RecoveryArbiter serialization."""
        terrain_name = self._terrain_fn()

        # Peek first (no side-effects) so a denied acquire doesn't waste budget.
        if not self._rec_arbiter.peek_edge_budget(self._edge_key):
            log.warning(
                "RouteFSM[%s]: recovery budget exhausted for this edge",
                self._edge_key,
            )
            self._transition(RouteFSMState.FAILED)
            return

        # Acquire lock — denied if a higher-priority recovery is already running.
        granted = self._rec_arbiter.acquire("FSM_RECOVERY", RecoveryLevel.MICRO_CORRECTION)
        if not granted:
            log.debug(
                "RouteFSM[%s]: recovery denied — %s already active",
                self._edge_key, self._rec_arbiter.active_source,
            )
            self._transition(RouteFSMState.FAILED)
            return

        # Lock acquired — now consume the budget slot.
        if not self._rec_arbiter.check_edge_budget(self._edge_key):
            # Should not happen (peek passed), but guard against TOCTOU.
            self._rec_arbiter.release("FSM_RECOVERY")
            self._transition(RouteFSMState.FAILED)
            return

        try:
            rec_result = self._recovery.escalate(
                from_level=RecoveryLevel.MICRO_CORRECTION,
                expected_anchor=self._edge.to_node,
                destination=self._edge.to_node,
                terrain_name=terrain_name,
                stop_event=self._stop,
            )
        finally:
            self._rec_arbiter.release("FSM_RECOVERY")

        self._recovery_lvl = rec_result.level
        self._confidence   = 0.0

        if rec_result.succeeded:
            self._transition(RouteFSMState.RECOVERING)
        else:
            self._transition(RouteFSMState.FAILED)

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _transition(self, new_state: RouteFSMState) -> None:
        log.debug("RouteFSM[%s]: %s → %s", self._edge_key, self._state.value, new_state.value)
        self._state_hist.append(self._state.value)
        self._state = new_state

    def _result(self, final_state: RouteFSMState) -> FSMResult:
        needs_replan = (
            final_state == RouteFSMState.RECOVERING or
            (final_state == RouteFSMState.FAILED and
             self._recovery_lvl is not None)
        )

        return FSMResult(
            final_state=final_state,
            confirmed_anchor=(
                self._edge.to_node
                if final_state == RouteFSMState.CONFIRMED
                else None
            ),
            confidence=self._confidence,
            elapsed_sec=round(time.monotonic() - self._t0, 3),
            recovery_level=self._recovery_lvl,
            needs_replan=needs_replan,
            drifted=self._drifted,
            temporal_confirmed=self._temporal_confirmed,
            temporal_marginal=self._temporal_marginal,
            temporal_frames=self._val_frames,
            telemetry=FSMTelemetry(
                edge_key=self._edge_key,
                state=final_state.value,
                elapsed_sec=round(time.monotonic() - self._t0, 3),
                confidence=self._confidence,
                validation_frames=self._val_frames,
                recovery_level=self._recovery_lvl.name if self._recovery_lvl else None,
                state_history=list(self._state_hist),
                timing=dict(self._timing),
            ),
        )

    @property
    def state(self) -> RouteFSMState:
        return self._state

    @property
    def telemetry(self) -> FSMTelemetry:
        return FSMTelemetry(
            edge_key=self._edge_key,
            state=self._state.value,
            elapsed_sec=round(time.monotonic() - self._t0, 3) if self._t0 else 0.0,
            confidence=self._confidence,
            validation_frames=self._val_frames,
            recovery_level=self._recovery_lvl.name if self._recovery_lvl else None,
            state_history=list(self._state_hist),
            timing=dict(self._timing),
        )
