"""
EdgeCalibration — online adaptive timing for RouteEdge traversals.

Static edge durations in nav_map.json/route_graph.py are baselines measured
at a known speed.  Actual traversal time varies with:
  - FPS variance (Roblox drops frames on high-activity servers)
  - Network latency spikes
  - Player speed buffs/debuffs
  - Server lag

EdgeCalibration tracks a rolling window of actual traversal times per edge
and computes an adaptive timeout hint so MovementExecutor never times out
too early or wastes time waiting.

Per-edge rolling statistics:
  duration samples (window=15) → mean ± 2σ → adaptive timeout
  success rate                  → reliability score [0, 1]
  recovery count                → recovery burden (higher = less reliable)
  drift events                  → drift_rate (higher = more unstable)

Calibrated duration formula:
  calibrated = max(baseline × 0.80, mean + 2.0 × std)

This ensures:
  - Never shorter than 80% of baseline (prevents premature timeout)
  - Never longer than 4× baseline (safety cap)

Dynamic edge score (used by planner):
  score = success_rate × (1 - recovery_rate × 0.5) × (1 - drift_rate × 0.3)
  → [0, 1]; higher = prefer this edge

Public API:
    ec = get_edge_calibration()
    ec.record("spawn_platform→hive_1_entrance", duration=2.8, success=True)
    hint = ec.calibrated_duration("spawn_platform→hive_1_entrance", baseline=2.5)
    score = ec.edge_score("spawn_platform→hive_1_entrance")
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional

from utils.logger import get_logger

log = get_logger(__name__)

_WINDOW      = 15
_MIN_SAMPLES = 3
_MAX_MULT    = 4.0   # max calibrated duration = baseline × this


@dataclass
class EdgeAttempt:
    duration:  float
    success:   bool
    recovered: bool
    drifted:   bool
    ts:        float = field(default_factory=time.monotonic)


@dataclass
class EdgeCalibrationStats:
    """Computed calibration stats for one edge."""
    key:              str
    attempts:         int
    mean_duration:    float
    std_duration:     float
    success_rate:     float
    recovery_rate:    float
    drift_rate:       float
    calibrated_mult:  float   # suggested multiplier vs baseline
    edge_score:       float   # planner preference [0, 1]
    confidence_tier:  str     # "reliable" / "marginal" / "unreliable"


class EdgeCalibration:
    """
    Online rolling-window calibration for all route edges.

    Thread-safe.
    Segment keys are "<from>→<to>" strings (matching RouteTelemetry convention).
    """

    def __init__(self) -> None:
        self._lock    = threading.Lock()
        self._history: Dict[str, Deque[EdgeAttempt]] = {}

    # ------------------------------------------------------------------ #
    # Recording                                                           #
    # ------------------------------------------------------------------ #

    def record(
        self,
        edge_key: str,
        duration: float,
        success: bool,
        recovered: bool = False,
        drifted: bool = False,
    ) -> None:
        """Record one traversal attempt."""
        with self._lock:
            if edge_key not in self._history:
                self._history[edge_key] = deque(maxlen=_WINDOW)
            self._history[edge_key].append(
                EdgeAttempt(duration=duration, success=success,
                            recovered=recovered, drifted=drifted)
            )

    # ------------------------------------------------------------------ #
    # Query                                                               #
    # ------------------------------------------------------------------ #

    def stats(self, edge_key: str) -> Optional[EdgeCalibrationStats]:
        """Compute stats for one edge. Returns None if no data."""
        with self._lock:
            hist = self._history.get(edge_key)
            if not hist:
                return None
            attempts = list(hist)

        n         = len(attempts)
        durations = [a.duration for a in attempts]
        successes = sum(1 for a in attempts if a.success)
        recoveries = sum(1 for a in attempts if a.recovered)
        drifts    = sum(1 for a in attempts if a.drifted)

        mean_d = sum(durations) / n
        if n >= 2:
            variance = sum((d - mean_d) ** 2 for d in durations) / n
            std_d    = math.sqrt(variance)
        else:
            std_d = mean_d * 0.15   # 15% uncertainty as prior

        success_rate  = successes / n
        recovery_rate = recoveries / n
        drift_rate    = drifts / n

        # Adaptive duration multiplier relative to mean
        # mean + 2σ gives ~95% coverage
        if n >= _MIN_SAMPLES:
            calibrated_mult = (mean_d + 2.0 * std_d) / max(mean_d, 0.1)
            calibrated_mult = min(calibrated_mult, _MAX_MULT)
        else:
            calibrated_mult = 1.5  # conservative prior

        # Edge score for planner
        edge_score = (
            success_rate *
            (1.0 - recovery_rate * 0.5) *
            (1.0 - drift_rate * 0.3)
        )

        if success_rate >= 0.85 and recovery_rate <= 0.15:
            tier = "reliable"
        elif success_rate >= 0.60:
            tier = "marginal"
        else:
            tier = "unreliable"

        return EdgeCalibrationStats(
            key=edge_key,
            attempts=n,
            mean_duration=round(mean_d, 3),
            std_duration=round(std_d, 3),
            success_rate=round(success_rate, 3),
            recovery_rate=round(recovery_rate, 3),
            drift_rate=round(drift_rate, 3),
            calibrated_mult=round(calibrated_mult, 3),
            edge_score=round(edge_score, 3),
            confidence_tier=tier,
        )

    def calibrated_duration(self, edge_key: str, baseline: float) -> float:
        """
        Return adaptive traversal timeout for this edge.

        If insufficient data, returns baseline × 1.3 (slightly conservative).
        Result is always in [baseline × 0.80, baseline × _MAX_MULT].
        """
        s = self.stats(edge_key)
        if s is None or s.attempts < _MIN_SAMPLES:
            return baseline * 1.3

        calibrated = baseline * s.calibrated_mult
        return max(baseline * 0.80, min(baseline * _MAX_MULT, calibrated))

    def edge_score(self, edge_key: str) -> float:
        """Return edge reliability score [0, 1]. 1.0 if no data (optimistic prior)."""
        s = self.stats(edge_key)
        if s is None or s.attempts < _MIN_SAMPLES:
            return 1.0  # assume reliable until proven otherwise
        return s.edge_score

    def is_reliable(self, edge_key: str) -> bool:
        s = self.stats(edge_key)
        if s is None or s.attempts < _MIN_SAMPLES:
            return True
        return s.confidence_tier == "reliable"

    def all_stats(self) -> Dict[str, EdgeCalibrationStats]:
        with self._lock:
            keys = list(self._history.keys())
        result = {}
        for k in keys:
            s = self.stats(k)
            if s:
                result[k] = s
        return result

    def problem_edges(self, threshold: float = 0.65) -> Dict[str, EdgeCalibrationStats]:
        return {
            k: s for k, s in self.all_stats().items()
            if s.attempts >= _MIN_SAMPLES and s.success_rate < threshold
        }

    def reset(self, edge_key: Optional[str] = None) -> None:
        with self._lock:
            if edge_key:
                self._history.pop(edge_key, None)
            else:
                self._history.clear()


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[EdgeCalibration] = None
_inst_lock = threading.Lock()


def get_edge_calibration() -> EdgeCalibration:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = EdgeCalibration()
    return _instance
