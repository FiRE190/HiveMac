"""
TemporalValidator — multi-frame checkpoint confirmation.

Single-frame detections are unreliable.  A template match can hit 0.70
on one frame and 0.30 on the next due to lighting changes, partial occlusion,
or animation frames.  Single-frame confirmation causes:
  - false positive anchors (flicker navigation)
  - premature traversal termination
  - incorrect recovery escalation

TemporalValidator accumulates CheckpointValidator results across multiple
frames over a short time window and only declares confirmed=True when:
  1. rolling_confidence ≥ CONFIRM_THRESHOLD
  2. at least MIN_FRAMES samples in the window
  3. confidence std deviation ≤ CONSISTENCY_THRESHOLD (stable detection)

This aggressively prevents:
  - single-frame false positives
  - noisy detection flicker
  - premature confirmation on marginal evidence

Evidence window:
  - Bounded by both frame count and time (WINDOW_SEC)
  - Old evidence expires automatically
  - Each observation ticked at ~_TICK_INTERVAL_SEC

Performance:
  - Only captures a new frame every _TICK_INTERVAL_SEC (≈45ms)
  - Reuses FrameManager cache — no duplicate MSS captures
  - Total validation time: MIN_FRAMES × 45ms ≈ 135ms minimum

Public API:
    tv = TemporalValidator(anchor_id="hive_1_entrance")
    result = tv.accumulate(
        terrain_name="GROUND",
        heading_deg=cam.heading,
        heading_unc=cam.heading_uncertainty,
        stop_event=stop_event,
    )
    if result.confirmed:
        localization_engine.confirm_anchor(...)
"""
from __future__ import annotations

import statistics
import threading
import time
from dataclasses import dataclass, field
from typing import Deque, List, Optional
from collections import deque

from navigation.checkpoint_validator import get_checkpoint_validator
from utils.logger import get_logger

log = get_logger(__name__)

# Frames and timing
_MIN_FRAMES            = 3       # minimum observations before confirming
_WINDOW_SEC            = 2.0     # max age of evidence
_TICK_INTERVAL_SEC     = 0.045   # time between validation samples

# Confirmation thresholds
_CONFIRM_THRESHOLD     = 0.58    # rolling mean must exceed this
_CONSISTENCY_THRESHOLD = 0.18    # std dev must be below this (stable)
_MARGINAL_THRESHOLD    = 0.42    # return marginal=True if mean >= this


@dataclass
class TemporalValidationResult:
    """
    Result of multi-frame temporal validation.

    confirmed:          True if rolling evidence meets all criteria
    marginal:           True if evidence is borderline (recovery_recommended)
    rolling_confidence: mean confidence across the evidence window
    frame_count:        number of frames in the window
    std_dev:            confidence std deviation (lower = more stable)
    evidence_window:    list of per-frame confidence values
    elapsed_sec:        total time spent accumulating
    drift_detected:     any frame reported drift
    """
    confirmed:          bool
    marginal:           bool
    rolling_confidence: float
    frame_count:        int
    std_dev:            float
    evidence_window:    List[float]
    elapsed_sec:        float
    drift_detected:     bool = False


@dataclass
class _FrameEvidence:
    confidence:     float
    drift_detected: bool
    ts:             float = field(default_factory=time.monotonic)


class TemporalValidator:
    """
    Multi-frame temporal accumulator for anchor confirmation.

    One instance per in-progress validation session.
    Call accumulate() to run the full validation loop.
    Call reset() to start over for a new anchor.
    """

    def __init__(
        self,
        anchor_id: str,
        min_frames: int = _MIN_FRAMES,
        window_sec: float = _WINDOW_SEC,
        confirm_threshold: float = _CONFIRM_THRESHOLD,
        consistency_threshold: float = _CONSISTENCY_THRESHOLD,
        max_frames: int = 8,
    ) -> None:
        self._anchor_id         = anchor_id
        self._min_frames        = min_frames
        self._window_sec        = window_sec
        self._confirm_threshold = confirm_threshold
        self._consistency       = consistency_threshold
        self._max_frames        = max_frames
        self._validator         = get_checkpoint_validator()
        self._buffer: Deque[_FrameEvidence] = deque(maxlen=max_frames)

    def reset(self) -> None:
        self._buffer.clear()

    # ------------------------------------------------------------------ #
    # Main accumulation loop                                              #
    # ------------------------------------------------------------------ #

    def accumulate(
        self,
        terrain_name: str,
        heading_deg: float,
        heading_unc: float,
        stop_event: threading.Event,
        route_success_rate: float = 0.5,
        speed_px_s: float = 0.0,
    ) -> TemporalValidationResult:
        """
        Run validation sampling loop until confirmed, max_frames reached,
        or stop_event set.

        Each iteration: CheckpointValidator.validate() → push evidence.
        After each frame: check if confirmed; return early on confirmation.
        """
        t0 = time.monotonic()
        self._buffer.clear()

        for frame_n in range(self._max_frames):
            if stop_event.is_set():
                break

            # Run single-frame validation
            v = self._validator.validate(
                expected_anchor=self._anchor_id,
                terrain_name=terrain_name,
                heading_deg=heading_deg,
                heading_unc=heading_unc,
                speed_px_s=speed_px_s,
                route_success_rate=route_success_rate,
            )

            self._buffer.append(_FrameEvidence(
                confidence=v.confidence,
                drift_detected=v.drift_detected,
            ))

            # Prune expired evidence
            cutoff = time.monotonic() - self._window_sec
            while self._buffer and self._buffer[0].ts < cutoff:
                self._buffer.popleft()

            # Evaluate after minimum frames collected
            if len(self._buffer) >= self._min_frames:
                result = self._evaluate(time.monotonic() - t0)
                if result.confirmed or result.marginal:
                    return result

            # Wait before next sample
            time.sleep(_TICK_INTERVAL_SEC)

        return self._evaluate(time.monotonic() - t0)

    # ------------------------------------------------------------------ #
    # Single-shot query (for callers that supply evidence externally)     #
    # ------------------------------------------------------------------ #

    def push_evidence(self, confidence: float, drift_detected: bool = False) -> None:
        """Push one frame of externally computed evidence."""
        self._buffer.append(_FrameEvidence(confidence=confidence, drift_detected=drift_detected))

    def evaluate(self) -> TemporalValidationResult:
        """Evaluate current buffer state (non-blocking)."""
        return self._evaluate(0.0)

    # ------------------------------------------------------------------ #
    # Internal                                                            #
    # ------------------------------------------------------------------ #

    def _evaluate(self, elapsed: float) -> TemporalValidationResult:
        if not self._buffer:
            return TemporalValidationResult(
                confirmed=False, marginal=False,
                rolling_confidence=0.0, frame_count=0,
                std_dev=0.0, evidence_window=[], elapsed_sec=elapsed,
            )

        confs  = [e.confidence for e in self._buffer]
        n      = len(confs)
        mean_c = sum(confs) / n
        std_c  = statistics.stdev(confs) if n >= 2 else 0.0
        drift  = any(e.drift_detected for e in self._buffer)

        # Drift penalty: if drift detected, reduce effective confidence
        effective = mean_c * (0.85 if drift else 1.0)

        confirmed = (
            n >= self._min_frames and
            effective >= self._confirm_threshold and
            std_c <= self._consistency
        )
        marginal = (
            not confirmed and
            n >= self._min_frames and
            effective >= _MARGINAL_THRESHOLD
        )

        log.debug(
            "TemporalValidator[%s]: n=%d mean=%.3f std=%.3f eff=%.3f → %s",
            self._anchor_id, n, mean_c, std_c, effective,
            "CONFIRMED" if confirmed else ("MARGINAL" if marginal else "FAILED"),
        )

        return TemporalValidationResult(
            confirmed=confirmed,
            marginal=marginal,
            rolling_confidence=round(effective, 3),
            frame_count=n,
            std_dev=round(std_c, 3),
            evidence_window=[round(c, 3) for c in confs],
            elapsed_sec=round(elapsed, 4),
            drift_detected=drift,
        )
