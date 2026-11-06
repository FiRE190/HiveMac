"""Human-like randomisation helpers stay inside their declared bounds."""
import math

from movement import randomizer


def test_jitter_stays_within_radius():
    for _ in range(200):
        x, y = randomizer.jitter(100.0, 200.0, radius=5.0)
        assert math.hypot(x - 100.0, y - 200.0) <= 5.0 * math.sqrt(2) + 1e-9


def test_random_duration_stays_within_variance():
    for _ in range(200):
        d = randomizer.random_duration(2.0, variance_pct=0.25)
        assert 1.5 - 1e-9 <= d <= 2.5 + 1e-9


def test_random_duration_never_negative():
    for _ in range(200):
        assert randomizer.random_duration(0.1, variance_pct=1.0) >= 0
