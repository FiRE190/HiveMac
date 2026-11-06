"""
Shared temporal computation utilities — single source of truth for
EMA smoothing and rolling-window statistics across all navigation modules.

AUTHORITY RULE: All EMA smoothing and rolling-window computations in the
navigation stack MUST use these utilities. No module may maintain its own
inline alpha-blend or ad-hoc deque trend calculation.

Modules and what they use:
  LocalizationEngine  — EMA for per-anchor confidence smoothing
  NavigationHealth    — RollingWindow for health trend detection
  EdgeCalibration     — RollingWindow for per-edge duration stats
  TemporalValidator   — RollingWindow for frame-evidence accumulation

This eliminates the timing desync risk from 4 independent rolling
windows using different timestamps and sample rates.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Deque, List, Optional, Tuple


class EMA:
    """
    Exponential moving average.

    Thread-safe.
    initial=None → first update() seeds the value directly (no prior belief).
    initial=v    → starts at v; first update applies EMA normally.

    This explicit initialization prevents the "EMA starting from zero" bug
    where the first high-confidence observation is diluted toward 0.
    """

    def __init__(self, alpha: float, initial: Optional[float] = None) -> None:
        if not (0.0 < alpha <= 1.0):
            raise ValueError(f"EMA alpha must be in (0, 1], got {alpha}")
        self._alpha  = alpha
        self._value  = initial
        self._seeded = initial is not None
        self._lock   = threading.Lock()

    def update(self, value: float) -> float:
        """Apply one EMA step. Returns new smoothed value."""
        with self._lock:
            if not self._seeded:
                self._value  = value
                self._seeded = True
            else:
                self._value = self._alpha * value + (1.0 - self._alpha) * self._value
            return self._value

    def reset(self, initial: Optional[float] = None) -> None:
        with self._lock:
            self._value  = initial
            self._seeded = initial is not None

    @property
    def value(self) -> float:
        with self._lock:
            return self._value if self._value is not None else 0.0

    @property
    def is_seeded(self) -> bool:
        with self._lock:
            return self._seeded


class RollingWindow:
    """
    Fixed-capacity rolling buffer of (timestamp, float) samples.

    Thread-safe. Provides mean, std, linear trend, and age-based pruning.
    All timestamps are monotonic (time.monotonic()).
    """

    def __init__(self, maxsize: int) -> None:
        self._maxsize = maxsize
        self._buf: Deque[Tuple[float, float]] = deque(maxlen=maxsize)
        self._lock = threading.Lock()

    def push(self, value: float, ts: Optional[float] = None) -> None:
        """Push one sample. ts defaults to time.monotonic()."""
        if ts is None:
            ts = time.monotonic()
        with self._lock:
            self._buf.append((ts, value))

    def prune(self, max_age_sec: float) -> None:
        """Remove samples older than max_age_sec."""
        cutoff = time.monotonic() - max_age_sec
        with self._lock:
            while self._buf and self._buf[0][0] < cutoff:
                self._buf.popleft()

    # ------------------------------------------------------------------ #
    # Stats (computed without lock to avoid holding it during math)       #
    # ------------------------------------------------------------------ #

    def _snapshot(self) -> List[Tuple[float, float]]:
        with self._lock:
            return list(self._buf)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._buf)

    @property
    def values(self) -> List[float]:
        return [v for _, v in self._snapshot()]

    @property
    def latest(self) -> Optional[float]:
        with self._lock:
            return self._buf[-1][1] if self._buf else None

    @property
    def mean(self) -> float:
        vals = self.values
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def std(self) -> float:
        vals = self.values
        n = len(vals)
        if n < 2:
            return 0.0
        m = sum(vals) / n
        return math.sqrt(sum((v - m) ** 2 for v in vals) / n)

    def trend_per_sec(self) -> float:
        """
        Linear trend of values over the window (value/second).
        Positive = increasing, negative = decreasing.
        Returns 0.0 if fewer than 2 samples.
        """
        snap = self._snapshot()
        if len(snap) < 2:
            return 0.0
        t0, v0 = snap[0]
        t1, v1 = snap[-1]
        dt = t1 - t0
        if dt < 0.01:
            return 0.0
        return (v1 - v0) / dt

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()
