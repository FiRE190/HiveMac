"""
Navigator — belief-state autonomous navigation orchestrator.

go_to(destination, stop_event) is the single public entry point for all
inter-node travel.

Architecture: Anchor → Checkpoint → Route Graph → RouteFSM → Executor
              + LocalizationEngine (probabilistic beliefs)
              + NavigationHealth   (proactive recovery)
              + EdgeCalibration    (adaptive timing)
              + TemporalValidator  (multi-frame confirmation)

Execution flow per edge:
  1. NavigationHealth.compute() — if CRITICAL, proactively escalate recovery
  2. RouteFSM.run() — handles: normalize → align → traverse → validate
     a. RouteFSMState.CONFIRMED → LocalizationEngine.confirm_anchor()
     b. RouteFSMState.RECOVERING → RecoveryManager already ran inside FSM
     c. RouteFSMState.FAILED → terminal; stop or replan
  3. EdgeCalibration.record() — adaptive timing for future runs
  4. RouteGraph.update_edge_score() — dynamic planner scoring
  5. LocalizationEngine.accumulate_drift() — ongoing belief decay
  6. NavigationDebugger.log_snapshot() — periodic observability

Architecture rules (immutable):
  - NEVER rely on timing alone — RouteFSM + TemporalValidator guard every edge
  - NEVER call pyautogui directly — only through MovementExecutor / primitives
  - NEVER call mss directly — only through FrameManager via detectors
  - NEVER assume traversal succeeded without temporal validation
  - LocalizationEngine is the SINGLE source of position truth
  - NavigationHealth drives PROACTIVE recovery, not reactive
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from navigation.types import NavEdge, NavPlan
from navigation.nav_map import get_nav_map
from navigation.path_planner import get_path_planner
from navigation.localizer import get_localizer
from navigation.landmark_detector import get_landmark_detector
from navigation.movement_executor import get_movement_executor
from navigation.camera import get_camera
from navigation.camera_state import get_camera_state_manager
from navigation.checkpoint_validator import get_checkpoint_validator
from navigation.route_telemetry import get_route_telemetry
from navigation.route_graph import get_route_graph
from navigation.edge_calibration import get_edge_calibration
from navigation.route_fsm import RouteFSM
from navigation.anchor_registry import get_anchor_registry
from navigation.recovery_arbiter import get_recovery_arbiter
from navigation.navigation_arbiter import (
    get_navigation_arbiter, ArbiterContext, NavigationAction,
)
from planning.recovery_manager import get_recovery_manager, RecoveryLevel
from world_model.localization_engine import get_localization_engine
from world_model.navigation_health import get_navigation_health
from observability.navigation_debugger import get_navigation_debugger
from perception.frame_manager import get_frame_manager
from utils.logger import get_logger

log = get_logger(__name__)

_MAX_REPLAN             = 3
_REPLAN_PAUSE           = 0.8
_PREPLAN_CONF_THRESHOLD = 0.30
_DEBUG_EVERY_N_EDGES    = 1
_HEALTH_CHECK_INTERVAL  = 3   # check NavigationHealth every N edges
_PASSIVE_DECAY_INTERVAL = 2.0 # seconds between passive drift decay ticks


class Navigator:
    """
    Session-level navigation manager with belief-state confidence tracking.

    One instance per farming session.
    Not thread-safe — use from the navigation/farming thread only.
    """

    def __init__(self) -> None:
        self._map        = get_nav_map()
        self._planner    = get_path_planner()
        self._loc        = get_localizer()              # legacy compatibility
        self._det        = get_landmark_detector()
        self._executor   = get_movement_executor()
        self._camera     = get_camera()
        self._csm        = get_camera_state_manager()
        self._validator  = get_checkpoint_validator()
        self._telemetry  = get_route_telemetry()
        self._rg         = get_route_graph()
        self._calibration = get_edge_calibration()
        self._registry   = get_anchor_registry()
        self._recovery   = get_recovery_manager()
        self._engine     = get_localization_engine()   # primary belief-state
        self._health     = get_navigation_health()
        self._debugger   = get_navigation_debugger()
        self._fm         = get_frame_manager()

        self._rec_arbiter  = get_recovery_arbiter()
        self._nav_arbiter  = get_navigation_arbiter()

        self._edge_count      = 0
        self._last_decay_tick = 0.0
        self._last_health_report = None

    # ------------------------------------------------------------------ #
    # Session setup                                                        #
    # ------------------------------------------------------------------ #

    def set_base_speed(self, px_per_sec: float) -> None:
        """Share a speed measured elsewhere (the farming loop's calibrator) with the executor."""
        if px_per_sec > 0:
            self._executor.set_base_speed(px_per_sec)

    def calibrate(self, stop_event: threading.Event) -> float:
        """Measure baseline movement speed. Call once per farming session."""
        speed = self._executor.calibrate(stop_event)
        log.info("Navigator calibrated: base_speed=%.1f px/s", speed)
        return speed

    def snap_spawn(self) -> None:
        """Call after death respawn — forces all state to spawn_platform."""
        self._executor.reset()
        self._loc.reset()
        self._loc.snap_to("spawn_platform")
        self._engine.snap_to("spawn_platform", 0.95)
        self._recovery.reset()
        self._rec_arbiter.reset()
        self._health.reset()          # clear stale trend data from prior session
        self._debugger.reset_session()
        self._last_health_report = None
        log.info("Navigator: snapped to spawn_platform")

    def snap_to(self, node_id: str, confidence: float = 0.95) -> None:
        """Manually anchor position (e.g. after cannon confirmed landing)."""
        self._loc.snap_to(node_id, confidence)
        self._engine.snap_to(node_id, confidence)

    # ------------------------------------------------------------------ #
    # Primary API                                                          #
    # ------------------------------------------------------------------ #

    def go_to(
        self,
        destination: str,
        stop_event: threading.Event,
        normalize_camera: bool = True,
    ) -> bool:
        """
        Navigate from current position to the named destination node.

        Returns True on successful arrival, False on stop_event or failure.
        """
        if stop_event.is_set():
            return False

        if not self._map.has_node(destination):
            log.error("Navigator: unknown destination '%s'", destination)
            return False

        # Use LocalizationEngine as canonical position source
        current = self._engine.dominant_anchor or self._loc.current_node
        if current == destination:
            log.debug("Navigator: already at '%s'", destination)
            return True

        self._engine.set_route(destination)
        self._recovery.reset()
        # Reset per-edge recovery budgets for this new navigation goal.
        # Budgets accumulate across replanning within one go_to() call (by design)
        # but must not starve fresh goals with leftover counts from prior routes.
        self._rec_arbiter.reset_all_edges()
        self._debugger.reset_session()

        if normalize_camera:
            self._csm.ensure_traversal_state(stop_event)
            if stop_event.is_set():
                return False

        # Pre-planning: scan when confidence is low
        if self._engine.dominant_confidence < _PREPLAN_CONF_THRESHOLD:
            log.info(
                "Navigator: low confidence (%.2f) — scanning for landmarks",
                self._engine.dominant_confidence,
            )
            self._try_quick_orient(stop_event)

        for replan_idx in range(_MAX_REPLAN):
            if stop_event.is_set():
                return False

            current = self._engine.dominant_anchor or self._loc.current_node
            plan    = self._planner.plan(current, destination)

            if plan is None:
                log.warning(
                    "Navigator: no path from '%s' to '%s' (attempt %d)",
                    current, destination, replan_idx + 1,
                )
                if replan_idx + 1 < _MAX_REPLAN:
                    time.sleep(_REPLAN_PAUSE)
                continue

            if len(plan) == 0:
                return True

            log.info(
                "Navigator: plan → '%s' via %d edge(s) (from=%s)",
                destination, len(plan), current,
            )

            success, needs_replan = self._execute_plan(plan, stop_event)
            if success:
                self._debugger.log_snapshot(level=20)
                return True
            if not needs_replan or stop_event.is_set():
                return False
            time.sleep(_REPLAN_PAUSE)

        log.error("Navigator: max replanning attempts reached for '%s'", destination)
        return False

    # ------------------------------------------------------------------ #
    # Plan execution                                                       #
    # ------------------------------------------------------------------ #

    def _execute_plan(
        self,
        plan: NavPlan,
        stop_event: threading.Event,
    ) -> tuple[bool, bool]:
        """
        Execute all edges via RouteFSM with proactive health checks.

        Returns (success, needs_replan).
        """
        for idx, edge in enumerate(plan.edges):
            if stop_event.is_set():
                return False, False

            log.debug(
                "Edge %d/%d: %s → %s [%s]",
                idx + 1, len(plan.edges),
                edge.from_node, edge.to_node, edge.method.value,
            )

            self._edge_count += 1
            edge_t0  = time.monotonic()
            edge_key = f"{edge.from_node}→{edge.to_node}"

            # Passive drift decay
            self._maybe_decay(edge_t0)

            # Refresh health every edge so ArbiterContext is never stale.
            # This is O(5 multiplications) — negligible vs. FSM cost.
            self._refresh_health(edge)

            # Proactive preempt only every N edges — uses the freshly computed report.
            if self._edge_count % _HEALTH_CHECK_INTERVAL == 0:
                if not self._maybe_health_preempt(edge, stop_event):
                    return False, True  # recovery happened, replan

            # Execute edge through FSM
            fsm = RouteFSM(
                edge=edge,
                terrain_fn=self._get_current_terrain,
                stop_event=stop_event,
            )
            self._debugger.set_fsm_state(fsm.state.value)
            fsm_result = fsm.run()
            self._debugger.set_fsm_state(fsm_result.final_state.value)
            self._debugger.set_validation_frames(fsm_result.telemetry.validation_frames if fsm_result.telemetry else 0)

            edge_elapsed = time.monotonic() - edge_t0
            drifted      = fsm_result.drifted

            if stop_event.is_set():
                return False, False

            # ── NavigationArbiter: single authority for post-validation decisions ──
            eng_state    = self._engine.state
            edge_rel     = self._calibration.edge_score(edge_key)
            health       = self._last_health_report

            arb_ctx = ArbiterContext(
                temporal_confirmed  = fsm_result.temporal_confirmed,
                temporal_marginal   = fsm_result.temporal_marginal,
                temporal_confidence = fsm_result.confidence,
                temporal_frame_count= fsm_result.temporal_frames,
                localization_stable = eng_state.localization_stable,
                dominant_confidence = eng_state.dominant_confidence,
                health_should_preempt = health.should_preempt if health else False,
                health_is_warning     = health.is_warning     if health else False,
                health_overall        = health.overall        if health else 1.0,
                edge_reliability    = edge_rel,
                edge_key            = edge_key,
                recovery_active     = self._rec_arbiter.is_active,
            )
            decision = self._nav_arbiter.decide(arb_ctx)
            log.debug("Arbiter[%s]: %s — %s", edge_key, decision.action.value, decision.rationale)

            success = decision.action == NavigationAction.PROCEED

            # Record outcomes (regardless of arbiter decision)
            self._calibration.record(
                edge_key,
                duration=edge_elapsed,
                success=success,
                recovered=fsm_result.recovery_level is not None,
                drifted=drifted,
            )
            self._telemetry.record(
                edge_key,
                success=success,
                elapsed=edge_elapsed,
                recovered=fsm_result.recovery_level is not None,
            )
            self._rg.update_edge_score(
                edge.from_node, edge.to_node,
                success=success,
                recovered=fsm_result.recovery_level is not None,
            )

            if decision.action == NavigationAction.PROCEED:
                conf = max(fsm_result.confidence, decision.confidence_floor)
                self._engine.confirm_anchor(edge.to_node, conf)
                self._loc.snap_to(edge.to_node, confidence=conf)
                log.debug("Edge done: confirmed '%s' conf=%.3f [%s]", edge.to_node, conf, decision.rationale)

            elif decision.action == NavigationAction.VALIDATE_MORE:
                # Gather additional frames then re-enter via replan
                log.info(
                    "Arbiter: VALIDATE_MORE on '%s' (+%d frames) — replanning",
                    edge_key, decision.extra_validation_frames,
                )
                return False, True

            elif decision.action in (NavigationAction.SOFT_RECOVER, NavigationAction.HARD_RECOVER):
                if fsm_result.recovery_level:
                    self._debugger.increment_recovery(fsm_result.recovery_level.name)
                # If recovery already ran inside FSM and produced a new anchor, preserve it
                if fsm_result.confirmed_anchor:
                    self._engine.confirm_anchor(fsm_result.confirmed_anchor, 0.75)
                    self._loc.snap_to(fsm_result.confirmed_anchor, confidence=0.75)
                elif fsm_result.needs_replan:
                    return False, True
                else:
                    self._engine.record_failure()
                    log.error("Navigator: arbiter %s on %s — terminal", decision.action.value, edge_key)
                    return False, False

            elif decision.action == NavigationAction.PAUSE:
                # Recovery is already active (R1) — wait and replan
                log.info("Arbiter: PAUSE on %s — recovery active, replanning", edge_key)
                return False, True

            else:
                # Default guard for any unhandled action
                self._engine.record_failure()
                return False, False

            # Periodic debug snapshot
            if self._edge_count % _DEBUG_EVERY_N_EDGES == 0:
                self._debugger.log_snapshot()

        return True, False

    # ------------------------------------------------------------------ #
    # Health computation (every edge) and proactive preempt (every N)   #
    # ------------------------------------------------------------------ #

    def _refresh_health(self, edge: NavEdge) -> None:
        """
        Compute and store the current health report for this edge.

        Called every edge so ArbiterContext always uses a fresh reading.
        Does NOT trigger any recovery action — that is done separately by
        _maybe_health_preempt() every _HEALTH_CHECK_INTERVAL edges.
        """
        eng_state = self._engine.state
        edge_key  = f"{edge.from_node}→{edge.to_node}"
        calib     = self._calibration.stats(edge_key)
        rec_rate  = calib.recovery_rate if calib else 0.0

        report = self._health.compute(
            localization_confidence=eng_state.dominant_confidence,
            heading_confidence=eng_state.heading_confidence,
            drift_score=eng_state.drift_score,
            route_success_rate=self._telemetry.success_rate(edge_key),
            recovery_rate=rec_rate,
        )
        self._last_health_report = report
        self._debugger.set_health(report.overall, report.tier)

    def _maybe_health_preempt(
        self,
        edge: NavEdge,
        stop_event: threading.Event,
    ) -> bool:
        """
        Act on the current health report. Invoke recovery if should_preempt.

        Assumes _refresh_health() was already called for this edge so the
        report is current. Returns True if safe to proceed, False if the
        navigator should replan from the recovery's new anchor.
        """
        report   = self._last_health_report
        edge_key = f"{edge.from_node}→{edge.to_node}"

        if not (report and report.should_preempt):
            return True

        log.warning(
            "NavigationHealth PROACTIVE: %s overall=%.2f — intervening before edge %s",
            report.tier, report.overall, edge_key,
        )

        # Peek first — don't waste a lock slot on an exhausted budget.
        if not self._rec_arbiter.peek_edge_budget(edge_key):
            log.debug(
                "NavigationHealth: preempt skipped — edge '%s' recovery budget exhausted",
                edge_key,
            )
            return True

        # HEALTH_PREEMPT (priority 1) cannot preempt FSM_RECOVERY (priority 5).
        if not self._rec_arbiter.acquire("HEALTH_PREEMPT", RecoveryLevel.HEADING_REALIGN):
            log.debug(
                "NavigationHealth: preempt denied — %s already active",
                self._rec_arbiter.active_source,
            )
            return True

        # Lock granted — consume the budget slot.
        if not self._rec_arbiter.check_edge_budget(edge_key):
            self._rec_arbiter.release("HEALTH_PREEMPT")
            return True

        try:
            terrain_name = self._get_current_terrain()
            rec_result = self._recovery.escalate(
                from_level=RecoveryLevel.HEADING_REALIGN,
                expected_anchor=edge.from_node,
                destination=edge.to_node,
                terrain_name=terrain_name,
                stop_event=stop_event,
            )
        finally:
            self._rec_arbiter.release("HEALTH_PREEMPT")

        if rec_result.succeeded and rec_result.new_anchor:
            self._engine.confirm_anchor(rec_result.new_anchor, 0.80)
            self._loc.snap_to(rec_result.new_anchor, confidence=0.80)
            self._debugger.increment_recovery(rec_result.level.name)
        return False  # trigger replan from new position

    # ------------------------------------------------------------------ #
    # Quick orient                                                         #
    # ------------------------------------------------------------------ #

    def _try_quick_orient(self, stop_event: threading.Event) -> None:
        """
        Scan current frame for any anchor. Updates LocalizationEngine.
        Called pre-planning when confidence is low.
        """
        terrain_name = self._get_current_terrain()
        result = get_checkpoint_validator().scan_for_any(
            terrain_name=terrain_name,
            heading_deg=self._csm.heading,
            heading_unc=self._csm.heading_uncertainty,
            speed_px_s=0.0,
        )

        if result and result.matched_anchor:
            self._engine.confirm_anchor(result.matched_anchor, result.confidence)
            self._loc.snap_to(result.matched_anchor, result.confidence)
            log.info(
                "Quick orient: located at '%s' conf=%.2f",
                result.matched_anchor, result.confidence,
            )
        else:
            # Fallback: legacy landmark detector scan
            frame = self._fm.full_frame()
            if frame is None:
                return
            readings = self._det.scan(frame)
            for r in readings:
                if r.confidence >= 0.55:
                    self._loc.observe(r)
                    self._engine.observe(r)
                    node = self._engine.dominant_anchor or self._loc.current_node
                    if node:
                        log.info(
                            "Quick orient (legacy): '%s' via '%s'",
                            node, r.name,
                        )
                    return

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _get_current_terrain(self) -> str:
        """Get current terrain name from TerrainEstimator. Defaults to 'GROUND'."""
        try:
            return self._executor.current_terrain_name()
        except Exception:
            return "GROUND"

    def _maybe_decay(self, now: float) -> None:
        """Trigger passive drift decay if enough time has passed."""
        if self._last_decay_tick == 0.0:
            self._last_decay_tick = now
            return
        elapsed = now - self._last_decay_tick
        if elapsed >= _PASSIVE_DECAY_INTERVAL:
            self._engine.decay_passive(elapsed)
            self._last_decay_tick = now


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[Navigator] = None
_inst_lock = threading.Lock()


def get_navigator() -> Navigator:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = Navigator()
    return _instance
