"""
CheckpointValidator — multi-signal arrival confirmation.

This is the core trust boundary for every traversal edge. After movement
stops (either by landmark detection or timeout fallback), the validator
runs all available signals and produces a structured verdict before the
navigator commits to snapping localizer state.

Validation pipeline (all signals run, then fused):
  1. Template match  — does the current frame contain the expected anchor?
  2. Terrain check   — is the current terrain what the anchor expects?
  3. Heading check   — does the camera heading match anchor expectation?
  4. Fusion engine   — combines the above with route history into one score
  5. Anchor registry — compare fused score against anchor.min_confidence

Result:
  CheckpointValidation(
    success:              bool    — did we arrive?
    confidence:           float   — how sure [0,1]?
    matched_anchor:       str     — which anchor was matched (or None)
    evidence:             dict    — per-signal values for debug/logging
    drift_detected:       bool    — are signals inconsistent (possible drift)?
    recovery_recommended: bool    — was this close enough to call marginal?
  )

NEVER:
  - trust a single signal
  - trust timing alone
  - trust movement completion alone

Public API:
    cv = get_checkpoint_validator()
    result = cv.validate(
        expected_anchor="hive_1_entrance",
        terrain_name=terrain.name,
        heading_deg=camera.heading,
        heading_unc=camera.heading_uncertainty,
        speed_px_s=0.0,
        route_success_rate=0.7,
        frame=None,      # None = use frame_manager
    )
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np

from navigation.anchor_registry import get_anchor_registry, AnchorDefinition
from perception.fusion_engine import get_fusion_engine, FusionResult
from perception.frame_manager import get_frame_manager
from perception.template_system import get_template_system
from utils.logger import get_logger

log = get_logger(__name__)

# Confidence thresholds for verdict
_SUCCESS_THRESHOLD   = 0.55   # checkpoint_confidence must exceed this to call it SUCCESS
_MARGINAL_THRESHOLD  = 0.38   # above this → soft success (unverified), recovery_recommended
_DRIFT_SIGNAL_SPREAD = 0.30   # if max-min signal spread > this → drift_detected=True

# Additional penalty applied when we expected to be at anchor but template fails
_TEMPLATE_REQUIRED_FLOOR = 0.30


@dataclass
class CheckpointValidation:
    """
    Verdict of one arrival check.

    success:              True if confidence >= _SUCCESS_THRESHOLD
    confidence:           fused checkpoint confidence [0, 1]
    matched_anchor:       expected anchor ID if confirmed, else None
    evidence:             per-signal breakdown (template, terrain, heading, …)
    drift_detected:       signal spread was wide — position may be wrong
    recovery_recommended: marginal match — proceed cautiously or recheck
    elapsed_sec:          how long validation took (for telemetry)
    """
    success:              bool
    confidence:           float
    matched_anchor:       Optional[str]
    evidence:             Dict[str, float] = field(default_factory=dict)
    drift_detected:       bool = False
    recovery_recommended: bool = False
    elapsed_sec:          float = 0.0


class CheckpointValidator:
    """
    Multi-signal validator for arrival confirmation.

    Stateless — every call to validate() is independent.
    Thread-safe (no mutable state beyond singleton references).
    """

    def __init__(self) -> None:
        self._registry = get_anchor_registry()
        self._fusion   = get_fusion_engine()
        self._ts       = get_template_system()
        self._fm       = get_frame_manager()

    # ------------------------------------------------------------------ #
    # Primary API                                                          #
    # ------------------------------------------------------------------ #

    def validate(
        self,
        expected_anchor: Optional[str],
        terrain_name: str,
        heading_deg: float,
        heading_unc: float,
        speed_px_s: float = 0.0,
        route_success_rate: float = 0.5,
        frame: Optional[np.ndarray] = None,
    ) -> CheckpointValidation:
        """
        Run multi-signal arrival check for expected_anchor.

        expected_anchor: the anchor we believe we just arrived at
        terrain_name:    current terrain (TerrainType.name)
        heading_deg:     camera heading estimate (degrees)
        heading_unc:     camera heading uncertainty (degrees)
        speed_px_s:      current movement speed (0 = stationary, expected post-arrival)
        route_success_rate: recent success rate for this route segment [0, 1]
        frame:           explicit frame (None = use frame_manager's latest)
        """
        t0 = time.monotonic()

        if frame is None:
            frame = self._fm.full_frame()

        anchor = self._registry.get(expected_anchor) if expected_anchor else None

        # Run fusion engine — it computes all sub-signals internally
        fusion: FusionResult = self._fusion.fuse(
            anchor_id=expected_anchor,
            frame=frame,
            terrain_name=terrain_name,
            heading_deg=heading_deg,
            heading_unc=heading_unc,
            speed_px_s=speed_px_s,
            route_success_rate=route_success_rate,
        )

        ckpt_conf = fusion.checkpoint_confidence
        signals   = fusion.signals

        # Additional gate: if we have an anchor but template is very weak,
        # reduce confidence — template is the most anchor-specific signal
        template_val = signals.get("template", 0.0)
        if anchor is not None and template_val < _TEMPLATE_REQUIRED_FLOOR:
            penalty   = (_TEMPLATE_REQUIRED_FLOOR - template_val) * 0.5
            ckpt_conf = max(0.0, ckpt_conf - penalty)
            log.debug(
                "CheckpointValidator: template weak (%.2f) — confidence penalized by %.2f",
                template_val, penalty,
            )

        ckpt_conf = round(ckpt_conf, 3)

        # Drift detection: wide signal spread suggests inconsistent perception
        sig_values     = list(signals.values())
        signal_spread  = (max(sig_values) - min(sig_values)) if sig_values else 0.0
        drift_detected = signal_spread >= _DRIFT_SIGNAL_SPREAD

        # Verdict
        success              = ckpt_conf >= _SUCCESS_THRESHOLD
        recovery_recommended = (not success) and (ckpt_conf >= _MARGINAL_THRESHOLD)
        matched_anchor       = expected_anchor if success else None

        elapsed = time.monotonic() - t0

        result = CheckpointValidation(
            success=success,
            confidence=ckpt_conf,
            matched_anchor=matched_anchor,
            evidence={
                **{f"signal_{k}": v for k, v in signals.items()},
                "localization_confidence": fusion.localization_confidence,
                "drift_probability":       fusion.drift_probability,
                "signal_spread":           round(signal_spread, 3),
            },
            drift_detected=drift_detected,
            recovery_recommended=recovery_recommended,
            elapsed_sec=round(elapsed, 4),
        )

        self._log_result(expected_anchor, result)
        return result

    # ------------------------------------------------------------------ #
    # Scan without a specific expected anchor                             #
    # ------------------------------------------------------------------ #

    def scan_for_any(
        self,
        terrain_name: str,
        heading_deg: float,
        heading_unc: float,
        speed_px_s: float = 0.0,
        frame: Optional[np.ndarray] = None,
    ) -> Optional[CheckpointValidation]:
        """
        Try to identify current location by scanning all anchors.

        Returns the best-matching CheckpointValidation if any anchor meets
        _MARGINAL_THRESHOLD, else None.  Used during recovery and pre-planning.
        """
        if frame is None:
            frame = self._fm.full_frame()

        best: Optional[CheckpointValidation] = None

        for anchor in self._registry.recovery_order():
            result = self.validate(
                expected_anchor=anchor.id,
                terrain_name=terrain_name,
                heading_deg=heading_deg,
                heading_unc=heading_unc,
                speed_px_s=speed_px_s,
                route_success_rate=0.5,
                frame=frame,
            )
            if result.confidence >= _MARGINAL_THRESHOLD:
                if best is None or result.confidence > best.confidence:
                    best = result
                if result.success:
                    break   # stop on first definitive match

        return best

    # ------------------------------------------------------------------ #
    # Internal                                                            #
    # ------------------------------------------------------------------ #

    def _log_result(
        self,
        expected_anchor: Optional[str],
        result: CheckpointValidation,
    ) -> None:
        verb = "CONFIRMED" if result.success else ("MARGINAL" if result.recovery_recommended else "FAILED")
        log.debug(
            "CheckpointValidator[%s]: %s conf=%.3f drift=%s signals=%s",
            expected_anchor or "?",
            verb,
            result.confidence,
            result.drift_detected,
            {k: v for k, v in result.evidence.items() if k.startswith("signal_")},
        )


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[CheckpointValidator] = None
import threading as _threading
_inst_lock = _threading.Lock()


def get_checkpoint_validator() -> CheckpointValidator:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = CheckpointValidator()
    return _instance
