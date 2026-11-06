"""
NavigationHealth — continuous navigation integrity scoring.

Computes a single navigation_health ∈ [0, 1] from multiple runtime
signals to enable PROACTIVE recovery — triggering intervention before
catastrophic failure rather than reacting after it.

Health factors and default weights:
  localization  (0.35) — dominant_confidence from LocalizationEngine
  heading       (0.20) — heading certainty from CameraStateManager
  drift         (0.20) — inverse of drift_score
  route_rel     (0.15) — recent edge reliability from RouteTelemetry
  recovery_load (0.10) — inverse of recent recovery rate

Thresholds:
  HEALTHY   ≥ 0.70 — proceed normally
  WARNING   0.50–0.70 — increase validation frequency, pad timeouts
  CRITICAL  < 0.50 — pause and invoke proactive recovery before next edge
  EMERGENCY < 0.30 — immediate escalation to ROUTE_RESTART or above

Trend detection:
  NavigationHealth tracks the last N health samples. If health is
  declining faster than _DECLINE_RATE_THRESHOLD per second, it
  signals should_preempt() = True even if current health is acceptable.

Public API:
    nh = get_navigation_health()
    report = nh.compute(loc_engine, csm, telemetry, active_route)
    if report.should_preempt:
        recovery_manager.escalate(...)
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

from utils.rolling_window import RollingWindow
from utils.logger import get_logger

log = get_logger(__name__)

# Health factor weights (must sum to 1.0)
_WEIGHTS = {
    "localization":  0.35,
    "heading":       0.20,
    "drift":         0.20,
    "route_rel":     0.15,
    "recovery_load": 0.10,
}

# Thresholds
_HEALTHY   = 0.70
_WARNING   = 0.50
_CRITICAL  = 0.30

# Trend detection: samples to keep and min decline rate to trigger preempt
_TREND_WINDOW   = 8
_DECLINE_RATE   = 0.06  # health units per second


@dataclass
class HealthReport:
    """Point-in-time navigation health snapshot."""
    overall:          float
    components:       Dict[str, float] = field(default_factory=dict)
    trend_per_sec:    float = 0.0      # negative = declining
    is_healthy:       bool  = True
    is_warning:       bool  = False
    is_critical:      bool  = False
    should_preempt:   bool  = False
    recommendation:   str   = ""

    @property
    def tier(self) -> str:
        if self.overall >= _HEALTHY:
            return "HEALTHY"
        if self.overall >= _WARNING:
            return "WARNING"
        if self.overall >= _CRITICAL:
            return "CRITICAL"
        return "EMERGENCY"


class NavigationHealth:
    """
    Proactive health monitor for the navigation runtime.

    Not thread-safe — call from the navigation thread only.
    """

    def __init__(self) -> None:
        # Uses shared RollingWindow utility (not an ad-hoc deque) so that
        # trend computation uses the same timestamp source as all other modules.
        self._window      = RollingWindow(maxsize=_TREND_WINDOW)
        self._last_report: Optional[HealthReport] = None

    def compute(
        self,
        localization_confidence: float,
        heading_confidence: float,
        drift_score: float,
        route_success_rate: float = 0.8,
        recovery_rate: float = 0.0,
        _ts: Optional[float] = None,
    ) -> HealthReport:
        """
        Compute current navigation health.

        localization_confidence: dominant_anchor confidence [0, 1]
        heading_confidence:      camera heading certainty [0, 1]
        drift_score:             accumulated drift [0, 1] (lower = better)
        route_success_rate:      recent segment success rate [0, 1]
        recovery_rate:           fraction of recent attempts needing recovery [0, 1]
        _ts:  TEST-ONLY — injected monotonic timestamp so unit tests can simulate
              real traversal timing without sleeping. NEVER pass this in production
              code. The underscore prefix is a deliberate "internal API" signal.
              Defaults to None → time.monotonic() inside RollingWindow.push().
        """
        components = {
            "localization":  localization_confidence,
            "heading":       heading_confidence,
            "drift":         max(0.0, 1.0 - drift_score),
            "route_rel":     route_success_rate,
            "recovery_load": max(0.0, 1.0 - recovery_rate * 2.0),
        }

        overall = sum(
            components[k] * _WEIGHTS[k]
            for k in _WEIGHTS
        )
        overall = round(min(1.0, max(0.0, overall)), 3)

        self._window.push(overall, ts=_ts)
        trend = self._window.trend_per_sec()

        is_critical    = overall < _WARNING
        is_warning     = not is_critical and overall < _HEALTHY
        is_healthy     = overall >= _HEALTHY
        should_preempt = is_critical or (trend < -_DECLINE_RATE and overall < _HEALTHY)

        rec = ""
        if overall < _CRITICAL:
            rec = "EMERGENCY: immediate HIVE_RESET or FULL_RESET required"
        elif is_critical:
            rec = "CRITICAL: invoke recovery before next edge"
        elif is_warning:
            rec = "WARNING: increase validation frequency"

        report = HealthReport(
            overall=overall,
            components={k: round(v, 3) for k, v in components.items()},
            trend_per_sec=round(trend, 4),
            is_healthy=is_healthy,
            is_warning=is_warning,
            is_critical=is_critical,
            should_preempt=should_preempt,
            recommendation=rec,
        )
        self._last_report = report

        if is_critical:
            log.warning(
                "NavigationHealth: %s overall=%.2f trend=%.3f/s [%s]",
                report.tier, overall, trend,
                " ".join(f"{k}={v:.2f}" for k, v in components.items()),
            )

        return report

    @property
    def last_report(self) -> Optional[HealthReport]:
        return self._last_report

    def reset(self) -> None:
        """
        Clear the health window and last report.

        Call after respawn or session reset so stale trend data from the
        previous session cannot trigger false preemptions at route start.
        """
        self._window.clear()
        self._last_report = None


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[NavigationHealth] = None
_inst_lock = threading.Lock()


def get_navigation_health() -> NavigationHealth:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = NavigationHealth()
    return _instance
