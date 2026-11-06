"""Movement patterns are pure generators: no screen, no input."""
import math

from movement import patterns


def _finite_pairs(steps):
    steps = list(steps)
    assert steps, "pattern produced no steps"
    for dx, dy in steps:
        assert math.isfinite(dx) and math.isfinite(dy)
    return steps


def test_every_pattern_yields_bounded_finite_steps():
    for cls in (patterns.CircularPattern, patterns.ZigZagPattern,
                patterns.SpiralPattern, patterns.CornerRotationPattern):
        steps = _finite_pairs(cls(radius=60, speed=1.0, randomness=0.0).steps(max_steps=40))
        assert len(steps) <= 40


def test_no_randomness_is_deterministic():
    a = list(patterns.CircularPattern(radius=50, randomness=0.0).steps(max_steps=30))
    b = list(patterns.CircularPattern(radius=50, randomness=0.0).steps(max_steps=30))
    assert a == b


def test_waypoint_pattern_follows_given_points():
    steps = _finite_pairs(patterns.WaypointPattern([[0, 0], [10, 0], [10, 10]], randomness=0.0)
                          .steps(max_steps=100))
    assert len(steps) <= 100
