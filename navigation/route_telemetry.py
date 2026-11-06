"""
RouteTelemetry — online rolling-window performance tracking per route segment.

Tracks per-segment runtime statistics so the planner and recovery manager can
make confidence-aware decisions:
  - Is this segment reliably traversable?
  - How much variance is there in traversal time?
  - How often does recovery get triggered here?

Adaptive calibration:
  If a segment's mean traversal time consistently deviates from the
  configured baseline, route_telemetry generates a duration adjustment
  factor so movement_executor can use a more accurate upper-bound timeout.

Rolling window: last _WINDOW attempts per segment.

Public API:
    rt = get_route_telemetry()
    rt.record("spawn→hive_1_entrance", success=True, elapsed=3.2, recovered=False)
    stats = rt.stats("spawn→hive_1_entrance")
    adj   = rt.duration_adjustment("spawn→hive_1_entrance")  # 1.0 = no change
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional, Tuple

from utils.logger import get_logger

log = get_logger(__name__)

_WINDOW      = 12   # attempts per segment kept in rolling window
_MIN_SAMPLES = 3    # minimum samples before adjustment is trusted


@dataclass
class SegmentStats:
    """Computed statistics for one route segment."""
    key:             str
    attempts:        int
    success_rate:    float          # [0, 1]
    mean_elapsed:    float          # seconds
    std_elapsed:     float          # seconds (0 if < 2 samples)
    recovery_rate:   float          # fraction of attempts that needed recovery
    duration_adj:    float          # multiplier for expected_duration (1.0 = no change)
    confidence_tier: str            # "reliable" / "marginal" / "unreliable"

    @property
    def is_reliable(self) -> bool:
        return self.confidence_tier == "reliable"


@dataclass
class _Attempt:
    success:   bool
    elapsed:   float
    recovered: bool
    ts:        float = field(default_factory=time.monotonic)


class RouteTelemetry:
    """
    Thread-safe rolling-window telemetry for route segments.

    Segment keys are typically "<from_node>→<to_node>" but can be any string.
    """

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._history: Dict[str, Deque[_Attempt]] = {}

    # ------------------------------------------------------------------ #
    # Recording                                                            #
    # ------------------------------------------------------------------ #

    def record(
        self,
        segment_key: str,
        success: bool,
        elapsed: float,
        recovered: bool = False,
    ) -> None:
        """Record the outcome of one traversal attempt."""
        with self._lock:
            if segment_key not in self._history:
                self._history[segment_key] = deque(maxlen=_WINDOW)
            self._history[segment_key].append(
                _Attempt(success=success, elapsed=elapsed, recovered=recovered)
            )
        log.debug("Telemetry[%s]: success=%s elapsed=%.1fs recovered=%s",
                  segment_key, success, elapsed, recovered)

    # ------------------------------------------------------------------ #
    # Query                                                                #
    # ------------------------------------------------------------------ #

    def stats(self, segment_key: str) -> Optional[SegmentStats]:
        """Return computed stats for a segment, or None if no data."""
        with self._lock:
            history = self._history.get(segment_key)
            if not history:
                return None
            attempts = list(history)

        n          = len(attempts)
        successes  = [a for a in attempts if a.success]
        elapsed    = [a.elapsed for a in attempts]
        recoveries = [a for a in attempts if a.recovered]

        success_rate  = len(successes) / n
        recovery_rate = len(recoveries) / n
        mean_e        = sum(elapsed) / n

        if n >= 2:
            variance = sum((e - mean_e) ** 2 for e in elapsed) / n
            std_e    = variance ** 0.5
        else:
            std_e = 0.0

        # Duration adjustment: if mean_elapsed deviates from expected (unknown here),
        # we expose the mean so callers can compare it against their baseline.
        # adj factor: if mean > baseline, duration_adj > 1 (need more time).
        # We can't know the baseline here — callers use mean_elapsed directly.
        duration_adj = 1.0  # baseline-agnostic; callers compute relative to their expected

        if success_rate >= 0.80:
            tier = "reliable"
        elif success_rate >= 0.50:
            tier = "marginal"
        else:
            tier = "unreliable"

        return SegmentStats(
            key=segment_key,
            attempts=n,
            success_rate=success_rate,
            mean_elapsed=mean_e,
            std_elapsed=std_e,
            recovery_rate=recovery_rate,
            duration_adj=duration_adj,
            confidence_tier=tier,
        )

    def success_rate(self, segment_key: str) -> float:
        """Returns [0, 1] success rate, or 0.5 if no data (neutral prior)."""
        s = self.stats(segment_key)
        return s.success_rate if s else 0.5

    def is_reliable(self, segment_key: str, threshold: float = 0.75) -> bool:
        """True if the segment has enough samples and a good success rate."""
        s = self.stats(segment_key)
        if s is None or s.attempts < _MIN_SAMPLES:
            return True  # assume reliable until proven otherwise
        return s.success_rate >= threshold

    def duration_hint(self, segment_key: str, baseline: float) -> float:
        """
        Return a suggested duration upper-bound for a segment.
        If we have enough samples, uses mean + 2×std; otherwise returns baseline.
        """
        s = self.stats(segment_key)
        if s is None or s.attempts < _MIN_SAMPLES:
            return baseline
        suggested = s.mean_elapsed + 2.0 * s.std_elapsed
        # Don't suggest less than 80% of baseline (prevents premature timeouts)
        return max(baseline * 0.80, suggested)

    def problem_segments(self, threshold: float = 0.60) -> Dict[str, SegmentStats]:
        """Return all segments with success rate below threshold."""
        result = {}
        with self._lock:
            keys = list(self._history.keys())
        for key in keys:
            s = self.stats(key)
            if s and s.attempts >= _MIN_SAMPLES and s.success_rate < threshold:
                result[key] = s
        return result

    def all_stats(self) -> Dict[str, SegmentStats]:
        """Return stats for all tracked segments."""
        result = {}
        with self._lock:
            keys = list(self._history.keys())
        for key in keys:
            s = self.stats(key)
            if s:
                result[key] = s
        return result

    def reset(self, segment_key: Optional[str] = None) -> None:
        """Reset history for one segment or all segments."""
        with self._lock:
            if segment_key:
                self._history.pop(segment_key, None)
            else:
                self._history.clear()


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[RouteTelemetry] = None
_inst_lock = threading.Lock()


def get_route_telemetry() -> RouteTelemetry:
    global _instance
    with _inst_lock:
        if _instance is None:
            _instance = RouteTelemetry()
    return _instance
