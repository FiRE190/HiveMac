"""
Movement primitives: WalkDuration, WalkUntilAnchor, StrafeAlign.

WalkDuration:
    Hold a key or key combo for a bounded duration.
    Stops early on anchor detection or stop_event.
    Time is an UPPER BOUND — perception stops it first.

WalkUntilAnchor:
    Hold a key, scanning every tick for a target anchor.
    Primary stopping condition: landmark confidence ≥ threshold.
    Secondary: hard timeout.

StrafeAlign:
    Strafe left/right in short bursts to center on a visual target.
    Used to align with cannon pads, hive doors, and field entry points.
"""
from __future__ import annotations

import threading
import time
from typing import List, Optional

from navigation.primitives.base import BasePrimitive, PrimitiveResult, TerminalReason
from execution.input_interface import get_input
from perception.frame_manager import get_frame_manager
from perception.template_system import get_template_system
from utils.logger import get_logger

log = get_logger(__name__)

# Flow tick: how often we sample perception during a walk
_FLOW_TICK = 0.045
# Scan for anchor every N ticks (N × _FLOW_TICK ≈ 135ms)
_SCAN_EVERY = 3
# Diagonal key separator: "wd" → ("w", "d")
def _split_key(k: str) -> List[str]:
    return list(k) if len(k) == 2 else [k]


class WalkDuration(BasePrimitive):
    """
    Hold movement key(s) for up to `duration` seconds.

    Stops early if:
      - stop_event is set
      - arrival_landmark is detected at or above arrival_conf
      - stall is detected (optional, checked if stall_sec > 0)

    Keys: single char ("w") or two-char diagonal ("wd").
    """

    def __init__(
        self,
        keys: str,
        duration: float,
        arrival_landmark: Optional[str] = None,
        arrival_conf: float = 0.50,
        stall_sec: float = 0.0,
    ) -> None:
        self._keys            = _split_key(keys)
        self._duration        = duration
        self._arrival_lm      = arrival_landmark
        self._arrival_conf    = arrival_conf
        self._stall_sec       = stall_sec
        self._input           = get_input()
        self._fm              = get_frame_manager()
        self._ts              = get_template_system()

    def execute(self, stop_event: threading.Event) -> PrimitiveResult:
        if self._check_stop(stop_event):
            return PrimitiveResult.stopped()

        t0            = time.monotonic()
        deadline      = t0 + self._duration
        tick_n        = 0
        best_lm_conf  = 0.0

        # Hold all keys
        for k in self._keys:
            self._input._pg and self._input._pg.keyDown(k)

        try:
            while True:
                if self._check_stop(stop_event):
                    return PrimitiveResult.stopped(self._elapsed(t0))

                now = time.monotonic()
                if now >= deadline:
                    return PrimitiveResult.timeout(
                        elapsed=self._elapsed(t0),
                        confidence=best_lm_conf,
                    )

                tick_n += 1
                if tick_n % _SCAN_EVERY == 0 and self._arrival_lm:
                    frame = self._fm.full_frame()
                    if frame is not None:
                        r = self._ts.match(self._arrival_lm, frame, threshold=0.0)
                        if r.confidence > best_lm_conf:
                            best_lm_conf = r.confidence
                        if r.confidence >= self._arrival_conf:
                            return PrimitiveResult(
                                success=True,
                                confidence=r.confidence,
                                elapsed_sec=self._elapsed(t0),
                                terminal_reason=TerminalReason.ANCHOR_FOUND,
                                evidence={"landmark_conf": r.confidence},
                            )

                time.sleep(_FLOW_TICK)
        finally:
            for k in self._keys:
                self._input._pg and self._input._pg.keyUp(k)


class WalkUntilAnchor(BasePrimitive):
    """
    Walk in direction `keys` until anchor_id is detected above threshold.

    Unlike WalkDuration, this primitive's entire purpose is finding the
    anchor — so it won't return SUCCESS until the anchor is confirmed or
    the timeout fires.

    max_duration is a hard safety cutoff (always required).
    """

    def __init__(
        self,
        keys: str,
        anchor_id: str,
        anchor_conf: float = 0.55,
        max_duration: float = 15.0,
        scan_group: Optional[str] = None,
    ) -> None:
        self._keys         = _split_key(keys)
        self._anchor_id    = anchor_id
        self._anchor_conf  = anchor_conf
        self._max_duration = max_duration
        self._scan_group   = scan_group
        self._input        = get_input()
        self._fm           = get_frame_manager()
        self._ts           = get_template_system()

    def execute(self, stop_event: threading.Event) -> PrimitiveResult:
        if self._check_stop(stop_event):
            return PrimitiveResult.stopped()

        t0       = time.monotonic()
        deadline = t0 + self._max_duration
        tick_n   = 0
        best     = 0.0

        for k in self._keys:
            self._input._pg and self._input._pg.keyDown(k)

        try:
            while True:
                if self._check_stop(stop_event):
                    return PrimitiveResult.stopped(self._elapsed(t0))

                if time.monotonic() >= deadline:
                    return PrimitiveResult(
                        success=False,
                        confidence=best,
                        elapsed_sec=self._elapsed(t0),
                        terminal_reason=TerminalReason.TIMEOUT,
                        message=f"anchor '{self._anchor_id}' not found before timeout",
                    )

                tick_n += 1
                if tick_n % _SCAN_EVERY == 0:
                    frame = self._fm.full_frame()
                    if frame is not None:
                        if self._scan_group:
                            mr = self._ts.best_in_group(self._scan_group, frame, threshold=0.0)
                            conf = mr.confidence if mr else 0.0
                            name = mr.name if mr else ""
                        else:
                            mr   = self._ts.match(self._anchor_id, frame, threshold=0.0)
                            conf = mr.confidence
                            name = mr.name

                        if conf > best:
                            best = conf
                        if conf >= self._anchor_conf:
                            return PrimitiveResult(
                                success=True,
                                confidence=conf,
                                elapsed_sec=self._elapsed(t0),
                                terminal_reason=TerminalReason.ANCHOR_FOUND,
                                evidence={"landmark_conf": conf, "landmark_name": name},
                            )

                time.sleep(_FLOW_TICK)
        finally:
            for k in self._keys:
                self._input._pg and self._input._pg.keyUp(k)


class StrafeAlign(BasePrimitive):
    """
    Strafe left/right in micro-bursts to align with a visual target.

    Strategy:
      1. Scan for target_landmark
      2. If found and centered (within center_tolerance): done
      3. If offset left: strafe right briefly; if offset right: strafe left
      4. Retry up to max_attempts times
      5. If never centered: return with best confidence reached

    center_tolerance: fraction of frame width; 0.15 = ±15% of frame center.
    """

    def __init__(
        self,
        target_landmark: str,
        center_tolerance: float = 0.15,
        strafe_burst_sec: float = 0.12,
        max_attempts: int = 6,
        target_conf: float = 0.45,
    ) -> None:
        self._target       = target_landmark
        self._tolerance    = center_tolerance
        self._burst        = strafe_burst_sec
        self._max_attempts = max_attempts
        self._target_conf  = target_conf
        self._input        = get_input()
        self._fm           = get_frame_manager()
        self._ts           = get_template_system()

    def execute(self, stop_event: threading.Event) -> PrimitiveResult:
        if self._check_stop(stop_event):
            return PrimitiveResult.stopped()

        t0   = time.monotonic()
        best = 0.0

        for attempt in range(self._max_attempts):
            if self._check_stop(stop_event):
                return PrimitiveResult.stopped(self._elapsed(t0))

            frame = self._fm.full_frame()
            if frame is None:
                time.sleep(_FLOW_TICK)
                continue

            r = self._ts.match(self._target, frame, threshold=0.0)
            if r.confidence > best:
                best = r.confidence

            if r.confidence < self._target_conf:
                time.sleep(_FLOW_TICK * 3)
                continue

            # Determine offset from frame center
            frame_cx = frame.shape[1] / 2.0
            target_cx = r.center[0] if r.center else frame_cx
            offset_frac = (target_cx - frame_cx) / frame_cx  # [-1, +1]

            if abs(offset_frac) <= self._tolerance:
                return PrimitiveResult(
                    success=True,
                    confidence=r.confidence,
                    elapsed_sec=self._elapsed(t0),
                    terminal_reason=TerminalReason.SUCCESS,
                    evidence={"offset_frac": round(offset_frac, 3), "conf": r.confidence},
                )

            # Strafe opposite to offset
            strafe_key = "d" if offset_frac < 0 else "a"
            if self._input._pg:
                self._input._pg.keyDown(strafe_key)
                time.sleep(self._burst)
                self._input._pg.keyUp(strafe_key)
            else:
                time.sleep(self._burst)

        return PrimitiveResult(
            success=False,
            confidence=best,
            elapsed_sec=self._elapsed(t0),
            terminal_reason=TerminalReason.ANCHOR_MISSED,
            message=f"StrafeAlign: '{self._target}' not centered after {self._max_attempts} attempts",
        )
