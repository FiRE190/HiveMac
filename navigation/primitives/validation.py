"""
ValidateAnchor primitive — run CheckpointValidator as an explicit step.

This primitive wraps the full multi-signal checkpoint validation pipeline
so it can be embedded in a RouteEdge execution sequence as a discrete step
rather than a post-edge implicit check.

Use when:
  - An edge has an intermediate confirmation point
  - A recovery sequence needs explicit verification before proceeding
  - High-value routes require extra confidence before committing

Returns PrimitiveResult:
  success=True   → validation passed (confidence ≥ SUCCESS_THRESHOLD)
  success=False  → validation failed; caller must decide whether to retry
  evidence dict  → full per-signal breakdown from CheckpointValidation
"""
from __future__ import annotations

import threading
from typing import Optional

from navigation.primitives.base import BasePrimitive, PrimitiveResult, TerminalReason
from navigation.checkpoint_validator import get_checkpoint_validator
from navigation.camera_state import get_camera_state_manager
from utils.logger import get_logger

log = get_logger(__name__)


class ValidateAnchor(BasePrimitive):
    """
    Run CheckpointValidator for the given anchor_id.

    anchor_id:         expected current location
    terrain_name:      current terrain (TerrainType.name)
    route_success_rate: recent success rate for context [0, 1]
    retry_count:       how many times to re-run validation if first fails
    retry_delay_sec:   wait between retries

    The camera state is read from CameraStateManager.
    """

    def __init__(
        self,
        anchor_id: str,
        terrain_name: str,
        route_success_rate: float = 0.5,
        retry_count: int = 0,
        retry_delay_sec: float = 0.3,
    ) -> None:
        self._anchor_id         = anchor_id
        self._terrain           = terrain_name
        self._route_success     = route_success_rate
        self._retry_count       = retry_count
        self._retry_delay       = retry_delay_sec
        self._validator         = get_checkpoint_validator()
        self._csm               = get_camera_state_manager()

    def execute(self, stop_event: threading.Event) -> PrimitiveResult:
        if self._check_stop(stop_event):
            return PrimitiveResult.stopped()

        import time
        t0 = time.monotonic()

        for attempt in range(self._retry_count + 1):
            if self._check_stop(stop_event):
                return PrimitiveResult.stopped(self._elapsed(t0))

            result = self._validator.validate(
                expected_anchor=self._anchor_id,
                terrain_name=self._terrain,
                heading_deg=self._csm.heading,
                heading_unc=self._csm.heading_uncertainty,
                speed_px_s=0.0,
                route_success_rate=self._route_success,
            )

            if result.success:
                return PrimitiveResult(
                    success=True,
                    confidence=result.confidence,
                    elapsed_sec=self._elapsed(t0),
                    terminal_reason=TerminalReason.SUCCESS,
                    evidence=result.evidence,
                    drift_detected=result.drift_detected,
                )

            if attempt < self._retry_count:
                log.debug(
                    "ValidateAnchor[%s]: attempt %d/%d failed (conf=%.3f) — retrying",
                    self._anchor_id, attempt + 1, self._retry_count + 1, result.confidence,
                )
                time.sleep(self._retry_delay)

        return PrimitiveResult(
            success=False,
            confidence=result.confidence,
            elapsed_sec=self._elapsed(t0),
            terminal_reason=TerminalReason.ANCHOR_MISSED,
            evidence=result.evidence,
            drift_detected=result.drift_detected,
            message=f"ValidateAnchor: '{self._anchor_id}' not confirmed after {self._retry_count + 1} attempt(s)",
        )
