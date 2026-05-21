"""
Humanization utilities: jitter, variable sleep, and micro-pauses.
All movement code should call through here instead of raw time.sleep.
"""
import random
import time
import math


def jitter(x: float, y: float, radius: float = 5.0) -> tuple[float, float]:
    """Add gaussian noise within `radius` pixels to (x, y)."""
    angle = random.uniform(0, 2 * math.pi)
    dist = abs(random.gauss(0, radius / 2))
    dist = min(dist, radius)
    return x + dist * math.cos(angle), y + dist * math.sin(angle)


def human_sleep(base_ms: float, variance_ms: float = 0.0) -> None:
    """Sleep for base_ms ± gaussian(variance_ms) milliseconds."""
    if variance_ms > 0:
        actual = base_ms + random.gauss(0, variance_ms / 2)
    else:
        actual = base_ms
    actual = max(10.0, actual)
    time.sleep(actual / 1000.0)


def micro_pause(chance: float = 0.08, min_ms: float = 50, max_ms: float = 250) -> None:
    """Occasionally pause to simulate human hesitation."""
    if random.random() < chance:
        time.sleep(random.uniform(min_ms, max_ms) / 1000.0)


def random_duration(base_sec: float, variance_pct: float = 0.15) -> float:
    """Return a duration near base_sec, varied by ±variance_pct."""
    delta = base_sec * variance_pct
    return base_sec + random.uniform(-delta, delta)


def interpolate_keys(
    duration_sec: float,
    keys: list[str],
    hold_ms_each: float = 200,
) -> list[tuple[str, float, float]]:
    """
    Build a randomized sequence of (key, hold_ms, pause_ms) pairs
    that fill approximately duration_sec seconds.
    """
    sequence = []
    elapsed = 0.0
    while elapsed < duration_sec:
        key = random.choice(keys)
        hold = hold_ms_each * random.uniform(0.7, 1.4)
        pause = random.uniform(40, 140)
        sequence.append((key, hold, pause))
        elapsed += (hold + pause) / 1000.0
    return sequence
