"""
AlignHeading primitive — camera alignment as an explicit execution step.

Wraps CameraStateManager.align_for_heading() so camera alignment can be
embedded in RouteEdge execution sequences as a discrete, accountable step
with a PrimitiveResult result (logged, tracked, retryable).

Useful before:
  - Walk segments that require a precise direction (diagonal runs, ramps)
  - Cannon alignment prior to UseCannon
  - Recovery sequences that need a known heading baseline

Returns:
  success=True    → heading within tolerance
  success=False   → could not align (stop_event, or too many tap corrections)
  confidence      → normalized heading certainty after align
"""
from __future__ import annotations

import threading

from navigation.primitives.base import BasePrimitive, PrimitiveResult, TerminalReason
from navigation.camera_state import get_camera_state_manager
from utils.logger import get_logger

log = get_logger(__name__)


class AlignHeading(BasePrimitive):
    """
    Align camera to target_deg before continuing.

    target_deg:  desired camera heading in degrees (0 = default forward)
    tolerance:   acceptable heading error in degrees
    force_norm:  if True, force a full F-reset even if heading is already close
    """

    def __init__(
        self,
        target_deg: float = 0.0,
        tolerance: float = 15.0,
        force_norm: bool = False,
    ) -> None:
        self._target    = target_deg
        self._tolerance = tolerance
        self._force     = force_norm
        self._csm       = get_camera_state_manager()

    def execute(self, stop_event: threading.Event) -> PrimitiveResult:
        if self._check_stop(stop_event):
            return PrimitiveResult.stopped()

        import time
        t0 = time.monotonic()

        if self._force:
            ok = self._csm.ensure_traversal_state(stop_event, force=True)
        else:
            ok = self._csm.align_for_heading(self._target, stop_event, tolerance=self._tolerance)

        if self._check_stop(stop_event):
            return PrimitiveResult.stopped(self._elapsed(t0))

        heading_conf = self._csm.heading_confidence

        return PrimitiveResult(
            success=ok,
            confidence=heading_conf,
            elapsed_sec=self._elapsed(t0),
            terminal_reason=TerminalReason.HEADING_OK if ok else TerminalReason.HEADING_FAIL,
            evidence={
                "heading_deg":         self._csm.heading,
                "heading_uncertainty": self._csm.heading_uncertainty,
                "target_deg":          self._target,
                "tolerance":           self._tolerance,
            },
        )


class NormalizeCamera(BasePrimitive):
    """
    F-reset camera to default heading (0°).

    Convenience wrapper for ensure_traversal_state() with force=False.
    Use at the start of a route or after any disorienting event.
    """

    def __init__(self) -> None:
        self._csm = get_camera_state_manager()

    def execute(self, stop_event: threading.Event) -> PrimitiveResult:
        if self._check_stop(stop_event):
            return PrimitiveResult.stopped()

        import time
        t0 = time.monotonic()

        ok = self._csm.ensure_traversal_state(stop_event)

        if self._check_stop(stop_event):
            return PrimitiveResult.stopped(self._elapsed(t0))

        return PrimitiveResult(
            success=ok,
            confidence=self._csm.heading_confidence,
            elapsed_sec=self._elapsed(t0),
            terminal_reason=TerminalReason.HEADING_OK if ok else TerminalReason.HEADING_FAIL,
            evidence={
                "heading_deg":         self._csm.heading,
                "heading_uncertainty": self._csm.heading_uncertainty,
            },
        )
