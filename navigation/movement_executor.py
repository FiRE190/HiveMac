"""
MovementExecutor — perception-driven edge execution.

ARCHITECTURE RULE: Time is a fallback, never the primary stopping condition.

Walk execution model:
  1. Hold movement key(s)
  2. Every tick: capture frame → optical flow → terrain estimate → landmark scan
  3. STOP when:
       a. arrival_landmark detected at sufficient confidence  [primary]
       b. Stop event is set                                   [interrupt]
       c. Timeout elapsed (edge.keys duration × TIMEOUT_MARGIN) [fallback]
  4. On stall (no flow for _STALL_SEC): release key → recovery → resume

The executor also feeds the camera heading model with real-time optical flow
so heading estimates stay accurate throughout traversal.

Timeout margin: edge key durations in nav_map.json are baseline at 16 studs/s.
The executor multiplies by TIMEOUT_MARGIN (2.5×) plus inverse speed-ratio to
ensure we never time out before a slow player could arrive.

Diagonal keys: two-char strings "sa", "wd" etc — both keys held simultaneously.

Camera rotation entries: "rot_rN" / "rot_lN" — call cam.rotate(±N), no hold.

Public API:
    executor = get_movement_executor()
    result   = executor.execute(edge, stop_event)
"""
from __future__ import annotations

import threading
import time
from typing import List, Optional

from navigation.types import NavEdge, EdgeMethod, EdgeResult, EdgeStatus, TerrainHint
from movement.terrain_estimator import TerrainEstimator, TerrainType
from movement.position_detector import PositionDetector
from detection.screen_capture import get_screen_capture
from utils.logger import get_logger

log = get_logger(__name__)

# Optical flow sample interval during key hold (s)
_FLOW_TICK = 0.045
# Consecutive stuck duration before triggering recovery (s)
_STALL_SEC = 1.5
# Minimum single key-hold duration — don't re-hold if less remaining
_BURST_MIN = 0.08
# Hard upper cap on any single burst (safety valve)
_BURST_MAX = 60.0
# Scan for arrival landmark every N flow ticks (N × _FLOW_TICK ≈ 135ms)
_LANDMARK_SCAN_EVERY = 3
# Multiply baseline key duration by this to get the timeout upper bound.
# 2.5× gives enough margin for a 40% slower-than-baseline player without
# timing out on a normal run.
_TIMEOUT_MARGIN = 2.5

# Terrain hint → baseline duration multiplier for timeout calculation
_TERRAIN_MULT: dict = {
    TerrainHint.RAMP_UP:   1.40,
    TerrainHint.RAMP_DOWN: 0.78,
    TerrainHint.BRIDGE:    1.10,
    TerrainHint.PLATFORM:  1.05,
    TerrainHint.GROUND:    1.00,
}


class MovementExecutor:
    """
    Executes NavEdges using perception-driven traversal primitives.

    One instance per session.  Not thread-safe — call from the navigation
    thread only.
    """

    def __init__(self) -> None:
        self._sc       = get_screen_capture()
        self._detector = PositionDetector()
        self._terrain  = TerrainEstimator()
        self._base_speed: float = 0.0

    # ------------------------------------------------------------------ #
    # Session setup                                                        #
    # ------------------------------------------------------------------ #

    def set_base_speed(self, px_per_sec: float) -> None:
        self._base_speed = px_per_sec
        self._terrain.set_base_speed(px_per_sec)

    def calibrate(self, stop_event: threading.Event) -> float:
        from movement.speed_calibrator import SpeedCalibrator
        calib = SpeedCalibrator()
        speed = calib.calibrate(stop_event)
        if speed > 0:
            self.set_base_speed(speed)
        return speed

    def reset(self) -> None:
        """Discard stale optical-flow state — call after teleports/respawns."""
        self._detector.reset()
        self._terrain.reset()

    # ------------------------------------------------------------------ #
    # Edge dispatch                                                        #
    # ------------------------------------------------------------------ #

    def execute(
        self,
        edge: NavEdge,
        stop_event: threading.Event,
        recovery=None,
    ) -> EdgeResult:
        """
        Execute one NavEdge.

        recovery: optional navigation.recovery.Recovery — called on stall.
        Returns EdgeResult indicating success, landmark-confirmed arrival,
        timeout (UNVERIFIED), stall, or failure.
        """
        t0 = time.monotonic()

        if stop_event.is_set():
            return EdgeResult(EdgeStatus.FAILED, edge, message="stop_event set")

        if edge.method == EdgeMethod.CANNON:
            ok = self._execute_cannon(edge, stop_event)
            status = EdgeStatus.SUCCESS if ok else EdgeStatus.FAILED

        elif edge.method in (EdgeMethod.GLIDER, EdgeMethod.JUMP_GLIDE):
            ok = self._execute_glider(edge, stop_event)
            status = EdgeStatus.SUCCESS if ok else EdgeStatus.FAILED

        elif edge.method == EdgeMethod.JUMP:
            self._tap_space()
            status = EdgeStatus.SUCCESS

        else:
            status = self._execute_walk(edge, stop_event, recovery)

        elapsed = time.monotonic() - t0
        return EdgeResult(status=status, edge=edge, elapsed_sec=elapsed)

    # ------------------------------------------------------------------ #
    # Walk                                                                 #
    # ------------------------------------------------------------------ #

    def _execute_walk(
        self,
        edge: NavEdge,
        stop_event: threading.Event,
        recovery,
    ) -> EdgeStatus:
        from navigation.camera import get_camera
        cam = get_camera()

        if edge.jump_at_start:
            self._tap_space()
            time.sleep(0.15)

        n_segments = sum(
            1 for key, _ in edge.keys
            if not (key.startswith("rot_r") or key.startswith("rot_l"))
        )
        segments_done = 0

        for key, base_dur in edge.keys:
            if stop_event.is_set():
                return EdgeStatus.FAILED

            # Camera rotation inline entries
            if key.startswith("rot_r") or key.startswith("rot_l"):
                try:
                    n = int(key[5:])
                except ValueError:
                    n = 1
                cam.rotate(n if key.startswith("rot_r") else -n)
                time.sleep(0.05)
                continue

            segments_done += 1
            is_last_segment = (segments_done == n_segments)

            # Only scan for arrival landmark on the last movement segment.
            # Intermediate segments use time bounds — we don't expect the
            # destination to be visible yet.
            arrival = edge.arrival_landmark if is_last_segment else None

            timeout = self._compute_timeout(base_dur, edge.terrain)
            result  = self._walk_burst(
                key, timeout, stop_event, recovery,
                arrival_landmark=arrival,
                arrival_conf=edge.arrival_conf,
                cam=cam,
            )

            if result == _BurstResult.ARRIVED:
                # Landmark confirmed during this segment
                break
            elif result == _BurstResult.STOPPED:
                return EdgeStatus.FAILED
            elif result == _BurstResult.STALLED:
                return EdgeStatus.STUCK if not stop_event.is_set() else EdgeStatus.FAILED
            # _BurstResult.TIMEOUT → continue to next segment / report UNVERIFIED

            time.sleep(0.06)

        if edge.jump_at_end:
            self._tap_space()
            time.sleep(0.20)

        return EdgeStatus.SUCCESS

    def _compute_timeout(self, base_dur: float, terrain: TerrainHint) -> float:
        """
        Convert a baseline duration into a generous upper-bound timeout.

        base_dur is calibrated at 16 studs/s (flat ground).
        Terrain hint adjusts for ramps.
        Speed ratio adjusts for current player speed vs baseline.
        TIMEOUT_MARGIN adds safety so a slow/lagging player still arrives.
        """
        hint_mult = _TERRAIN_MULT.get(terrain, 1.0)
        if self._base_speed > 0:
            ratio = self._terrain.mean_speed_ratio()
            # If slower than base, timeout must be longer (÷ ratio < 1).
            # Don't let extremely fast ratio shrink timeout below base.
            ratio = max(0.4, min(2.0, ratio))
        else:
            ratio = 1.0
        dur = (base_dur * hint_mult / ratio) * _TIMEOUT_MARGIN
        return max(_BURST_MIN, min(_BURST_MAX, dur))

    def _walk_burst(
        self,
        key: str,
        timeout: float,
        stop_event: threading.Event,
        recovery,
        arrival_landmark: Optional[str],
        arrival_conf: float,
        cam,
    ) -> "_BurstResult":
        """
        Hold key(s) while monitoring perception signals.

        Stopping conditions (priority order):
          1. arrival_landmark detected at ≥ arrival_conf    → ARRIVED
          2. stop_event set                                  → STOPPED
          3. Unrecoverable stall                             → STALLED
          4. timeout elapsed                                 → TIMEOUT  (fallback)

        key: "w", "sa", "wd" etc (1 or 2 chars for diagonal)
        """
        from execution.input_interface import get_input
        from navigation.landmark_detector import get_landmark_detector
        from navigation.debug_stream import get_debug_stream

        inp      = get_input()
        detector = get_landmark_detector()
        dbg      = get_debug_stream()

        keys: List[str] = list(key)  # "sa" → ["s", "a"]

        stall_start: Optional[float] = None
        scan_counter  = 0
        t0 = time.monotonic()

        log.debug("Walk burst: key=%s timeout=%.2fs arrival=%s", key, timeout, arrival_landmark)
        dbg.event("burst_start", key=key, timeout=timeout, arrival=arrival_landmark)

        def _press_all() -> None:
            if inp.available:
                for k in keys:
                    inp._pg.keyDown(k)
                    with inp._held_lock:
                        inp._held.add(k)

        def _release_all() -> None:
            if inp.available:
                for k in keys:
                    try:
                        inp._pg.keyUp(k)
                        with inp._held_lock:
                            inp._held.discard(k)
                    except Exception:
                        pass

        result = _BurstResult.TIMEOUT  # default if we exit via timeout

        try:
            _press_all()

            while time.monotonic() - t0 < timeout:
                if stop_event.is_set():
                    result = _BurstResult.STOPPED
                    break

                elapsed = time.monotonic() - t0
                frame   = self._sc.capture_full()
                speed_px_s: float = 0.0
                terrain_str: str  = "unknown"

                if frame is not None:
                    d = self._detector.push_frame(frame)

                    if d and d.confidence > 0.15:
                        sample = self._terrain.update(d)
                        speed_px_s  = d.speed
                        terrain_str = sample.terrain.name

                        # Feed optical flow into camera heading model
                        if d.speed > 0:
                            cam.refine_from_flow(d.dx, d.dy, d.speed)

                        # Stall detection
                        if sample.terrain == TerrainType.STUCK and self._base_speed > 0:
                            if stall_start is None:
                                stall_start = time.monotonic()
                            elif time.monotonic() - stall_start >= _STALL_SEC:
                                log.warning("Walk: stall detected key=%s elapsed=%.1fs", key, elapsed)
                                dbg.event("stall_detected", key=key, elapsed=elapsed)
                                _release_all()
                                if recovery:
                                    recovery.unstick(stop_event)
                                stall_start = None
                                if stop_event.is_set():
                                    result = _BurstResult.STOPPED
                                    break
                                remaining = timeout - (time.monotonic() - t0)
                                if remaining > _BURST_MIN:
                                    _press_all()
                                else:
                                    result = _BurstResult.STALLED
                                    break
                        else:
                            stall_start = None

                    # Landmark scan (every N ticks to amortise cost)
                    scan_counter += 1
                    if arrival_landmark and scan_counter % _LANDMARK_SCAN_EVERY == 0:
                        readings = detector.scan(frame, [arrival_landmark])
                        lm_pairs = [(r.name, r.confidence) for r in readings]

                        if readings and readings[0].confidence >= arrival_conf:
                            log.info(
                                "Walk: arrived at '%s' (conf=%.2f) after %.1fs",
                                arrival_landmark, readings[0].confidence, elapsed,
                            )
                            dbg.event("arrival_detected", landmark=arrival_landmark,
                                      conf=readings[0].confidence, elapsed=elapsed)
                            result = _BurstResult.ARRIVED
                            break

                        # Debug telemetry
                        dbg.nav_frame(
                            key=key, elapsed=elapsed,
                            speed_px_s=speed_px_s, terrain=terrain_str,
                            stalled=(stall_start is not None),
                            heading_deg=cam.heading,
                            heading_uncertainty=cam.heading_uncertainty,
                            landmarks=lm_pairs,
                        )
                    else:
                        dbg.nav_frame(
                            key=key, elapsed=elapsed,
                            speed_px_s=speed_px_s, terrain=terrain_str,
                            stalled=(stall_start is not None),
                            heading_deg=cam.heading,
                            heading_uncertainty=cam.heading_uncertainty,
                        )

                time.sleep(_FLOW_TICK)

        finally:
            _release_all()
            if result == _BurstResult.TIMEOUT:
                log.debug("Walk: timeout after %.1fs (key=%s arrival=%s)", timeout, key, arrival_landmark)
                dbg.event("burst_timeout", key=key, timeout=timeout, arrival=arrival_landmark)

        return result

    # ------------------------------------------------------------------ #
    # Cannon                                                               #
    # ------------------------------------------------------------------ #

    def _execute_cannon(self, edge: NavEdge, stop_event: threading.Event) -> bool:
        from movement.cannon_controller import CannonController
        cannon = CannonController()
        ok = cannon.execute(
            cannon_key=edge.cannon_key,
            align_keys=edge.cannon_align_keys,
            expected_air_time=edge.expected_air_time_sec,
            base_speed=self._base_speed,
            stop_event=stop_event,
        )
        if ok:
            self.reset()
        return ok

    # ------------------------------------------------------------------ #
    # Glider                                                               #
    # ------------------------------------------------------------------ #

    def _execute_glider(self, edge: NavEdge, stop_event: threading.Event) -> bool:
        from movement.glider_controller import GliderController
        glider = GliderController()
        ok = glider.execute(
            glider_key=edge.glider_key,
            expected_glide_sec=edge.expected_glide_sec,
            base_speed=self._base_speed,
            do_jump=(edge.method == EdgeMethod.JUMP_GLIDE),
            stop_event=stop_event,
        )
        if ok:
            self.reset()
        return ok

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _tap_space(self) -> None:
        try:
            from execution.input_interface import get_input
            get_input().tap_key("space")
        except Exception as exc:
            log.debug("Space tap error: %s", exc)


# ── Internal enum for burst result ────────────────────────────────────────────

class _BurstResult:
    ARRIVED = "arrived"    # landmark detected
    TIMEOUT = "timeout"    # time elapsed (fallback)
    STOPPED = "stopped"    # stop_event
    STALLED = "stalled"    # unrecoverable


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[MovementExecutor] = None
_inst_lock = threading.Lock()


def get_movement_executor() -> MovementExecutor:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = MovementExecutor()
    return _instance
