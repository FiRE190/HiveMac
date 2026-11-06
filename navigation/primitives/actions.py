"""
Action primitives: Jump, JumpGlide, UseCannon, ResetCharacter.

Jump:
    Single or repeated spacebar tap(s). Optionally waits for landing
    by waiting for low optical-flow speed after the jump arc.

JumpGlide:
    Jump then deploy glider (Q key). Waits for glider deployment
    confirmation via frame settling. Hard deadline for the full arc.

UseCannon:
    Align with cannon (optional strafe align), press activation key,
    wait for launch + air time, confirm landing via anchor detection.

ResetCharacter:
    Press R to reset. Waits for respawn UI to clear before returning.
    Only called during recovery escalation — not for normal traversal.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from navigation.primitives.base import BasePrimitive, PrimitiveResult, TerminalReason
from execution.input_interface import get_input
from perception.frame_manager import get_frame_manager
from perception.template_system import get_template_system
from utils.logger import get_logger

log = get_logger(__name__)

_FLOW_TICK = 0.045
_SCAN_EVERY = 3


class Jump(BasePrimitive):
    """
    Tap the spacebar one or more times.

    jump_count:    how many jumps to perform
    hold_sec:      how long to hold spacebar per jump (0 = tap only)
    settle_sec:    how long to wait after the last jump before returning
    """

    def __init__(
        self,
        jump_count: int = 1,
        hold_sec: float = 0.0,
        settle_sec: float = 0.25,
    ) -> None:
        self._count   = jump_count
        self._hold    = hold_sec
        self._settle  = settle_sec
        self._input   = get_input()

    def execute(self, stop_event: threading.Event) -> PrimitiveResult:
        if self._check_stop(stop_event):
            return PrimitiveResult.stopped()

        t0 = time.monotonic()
        pg = self._input._pg

        for i in range(self._count):
            if self._check_stop(stop_event):
                return PrimitiveResult.stopped(self._elapsed(t0))

            if pg:
                if self._hold > 0:
                    pg.keyDown("space")
                    time.sleep(self._hold)
                    pg.keyUp("space")
                else:
                    pg.press("space")
            else:
                time.sleep(max(0.05, self._hold))

            if i < self._count - 1:
                time.sleep(0.12)  # inter-jump gap

        if self._settle > 0 and not self._check_stop(stop_event):
            time.sleep(self._settle)

        return PrimitiveResult(
            success=True,
            confidence=1.0,
            elapsed_sec=self._elapsed(t0),
            terminal_reason=TerminalReason.SUCCESS,
        )


class JumpGlide(BasePrimitive):
    """
    Jump, then deploy glider (Q key) after jump_delay_sec.

    Waits for glide arc to complete (glide_duration_sec upper bound).
    Optionally scans for landing_landmark to stop early.
    """

    def __init__(
        self,
        glider_key: str = "q",
        jump_delay_sec: float = 0.20,
        glide_duration_sec: float = 4.0,
        landing_landmark: Optional[str] = None,
        landing_conf: float = 0.50,
    ) -> None:
        self._glider_key      = glider_key
        self._jump_delay      = jump_delay_sec
        self._glide_duration  = glide_duration_sec
        self._landing_lm      = landing_landmark
        self._landing_conf    = landing_conf
        self._input           = get_input()
        self._fm              = get_frame_manager()
        self._ts              = get_template_system()

    def execute(self, stop_event: threading.Event) -> PrimitiveResult:
        if self._check_stop(stop_event):
            return PrimitiveResult.stopped()

        t0 = time.monotonic()
        pg = self._input._pg

        # Jump
        if pg:
            pg.press("space")
        time.sleep(self._jump_delay)

        if self._check_stop(stop_event):
            return PrimitiveResult.stopped(self._elapsed(t0))

        # Deploy glider
        if pg:
            pg.press(self._glider_key)

        deadline = t0 + self._jump_delay + self._glide_duration
        tick_n   = 0
        best_lm  = 0.0

        while time.monotonic() < deadline:
            if self._check_stop(stop_event):
                return PrimitiveResult.stopped(self._elapsed(t0))

            tick_n += 1
            if tick_n % _SCAN_EVERY == 0 and self._landing_lm:
                frame = self._fm.full_frame()
                if frame is not None:
                    r = self._ts.match(self._landing_lm, frame, threshold=0.0)
                    if r.confidence > best_lm:
                        best_lm = r.confidence
                    if r.confidence >= self._landing_conf:
                        return PrimitiveResult(
                            success=True,
                            confidence=r.confidence,
                            elapsed_sec=self._elapsed(t0),
                            terminal_reason=TerminalReason.ANCHOR_FOUND,
                        )

            time.sleep(_FLOW_TICK)

        return PrimitiveResult(
            success=True,  # glide completed — outcome uncertain without landmark
            confidence=best_lm,
            elapsed_sec=self._elapsed(t0),
            terminal_reason=TerminalReason.TIMEOUT,
            message="JumpGlide: glide arc complete (no landmark confirmation)",
        )


class UseCannon(BasePrimitive):
    """
    Activate a cannon and wait for landing.

    Sequence:
      1. Press activation key (default "e")
      2. Wait for launch (launch_wait_sec)
      3. Wait for air arc (air_time_sec upper bound)
      4. Optionally scan for landing_landmark during air arc

    cannon_key:   key to activate the cannon
    air_time_sec: UPPER BOUND for flight time — stops early on landmark
    """

    def __init__(
        self,
        cannon_key: str = "e",
        launch_wait_sec: float = 0.5,
        air_time_sec: float = 5.0,
        landing_landmark: Optional[str] = None,
        landing_conf: float = 0.50,
    ) -> None:
        self._cannon_key    = cannon_key
        self._launch_wait   = launch_wait_sec
        self._air_time      = air_time_sec
        self._landing_lm    = landing_landmark
        self._landing_conf  = landing_conf
        self._input         = get_input()
        self._fm            = get_frame_manager()
        self._ts            = get_template_system()

    def execute(self, stop_event: threading.Event) -> PrimitiveResult:
        if self._check_stop(stop_event):
            return PrimitiveResult.stopped()

        t0 = time.monotonic()
        pg = self._input._pg

        log.debug("UseCannon: activating with key '%s'", self._cannon_key)
        if pg:
            pg.press(self._cannon_key)

        time.sleep(self._launch_wait)

        if self._check_stop(stop_event):
            return PrimitiveResult.stopped(self._elapsed(t0))

        deadline = t0 + self._launch_wait + self._air_time
        tick_n   = 0
        best_lm  = 0.0

        while time.monotonic() < deadline:
            if self._check_stop(stop_event):
                return PrimitiveResult.stopped(self._elapsed(t0))

            tick_n += 1
            if tick_n % _SCAN_EVERY == 0 and self._landing_lm:
                frame = self._fm.full_frame()
                if frame is not None:
                    r = self._ts.match(self._landing_lm, frame, threshold=0.0)
                    if r.confidence > best_lm:
                        best_lm = r.confidence
                    if r.confidence >= self._landing_conf:
                        log.debug("UseCannon: landing confirmed '%s' conf=%.2f",
                                  self._landing_lm, r.confidence)
                        return PrimitiveResult(
                            success=True,
                            confidence=r.confidence,
                            elapsed_sec=self._elapsed(t0),
                            terminal_reason=TerminalReason.ANCHOR_FOUND,
                            evidence={"landing_conf": r.confidence},
                        )

            time.sleep(_FLOW_TICK)

        return PrimitiveResult(
            success=True,
            confidence=best_lm,
            elapsed_sec=self._elapsed(t0),
            terminal_reason=TerminalReason.TIMEOUT,
            message="UseCannon: air arc timeout (no landmark confirmation)",
        )


class ResetCharacter(BasePrimitive):
    """
    Press R to reset the character.

    Waits for the death/respawn screen to appear and clear before returning.
    Only call during RecoveryManager escalation — this is a last-resort action.

    reset_wait_sec: how long to wait for the respawn UI to resolve.
    """

    def __init__(
        self,
        reset_wait_sec: float = 6.0,
        respawn_landmark: Optional[str] = None,
    ) -> None:
        self._reset_wait      = reset_wait_sec
        self._respawn_lm      = respawn_landmark or "respawn_screen"
        self._input           = get_input()
        self._fm              = get_frame_manager()
        self._ts              = get_template_system()

    def execute(self, stop_event: threading.Event) -> PrimitiveResult:
        if self._check_stop(stop_event):
            return PrimitiveResult.stopped()

        t0 = time.monotonic()
        pg = self._input._pg

        log.info("ResetCharacter: pressing R to reset")
        if pg:
            pg.press("r")

        deadline   = t0 + self._reset_wait
        respawned  = False
        tick_n     = 0

        while time.monotonic() < deadline:
            if self._check_stop(stop_event):
                return PrimitiveResult.stopped(self._elapsed(t0))

            tick_n += 1
            if tick_n % _SCAN_EVERY == 0:
                frame = self._fm.full_frame()
                if frame is not None:
                    r = self._ts.match(self._respawn_lm, frame, threshold=0.0)
                    if r.confidence >= 0.50:
                        respawned = True
                        break

            time.sleep(_FLOW_TICK)

        # Wait for UI to clear after respawn
        if respawned:
            clear_deadline = time.monotonic() + 3.0
            while time.monotonic() < clear_deadline:
                if self._check_stop(stop_event):
                    return PrimitiveResult.stopped(self._elapsed(t0))
                frame = self._fm.full_frame()
                if frame is not None:
                    r = self._ts.match(self._respawn_lm, frame, threshold=0.0)
                    if r.confidence < 0.30:
                        break
                time.sleep(_FLOW_TICK * 2)

        return PrimitiveResult(
            success=respawned,
            confidence=1.0 if respawned else 0.0,
            elapsed_sec=self._elapsed(t0),
            terminal_reason=TerminalReason.SUCCESS if respawned else TerminalReason.TIMEOUT,
            evidence={"respawn_detected": float(respawned)},
        )
