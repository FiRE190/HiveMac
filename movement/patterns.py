"""
Movement pattern generators for field farming.

Each pattern yields successive (dx, dy) offsets relative to a start point.
The MovementController applies these with randomization layered on top.

Usage:
    pattern = PatternFactory.create("circular", radius=60, speed=1.0, randomness=0.3)
    for dx, dy in pattern.steps(max_steps=200):
        ...move to (origin_x + dx, origin_y + dy)...
"""
import math
import random
from abc import ABC, abstractmethod
from typing import Iterator


class MovementPattern(ABC):
    def __init__(self, radius: float = 60, speed: float = 1.0, randomness: float = 0.3):
        self.radius = radius
        self.speed = speed
        self.randomness = randomness
        self._step = 0

    def _add_noise(self, dx: float, dy: float) -> tuple[float, float]:
        if self.randomness <= 0:
            return dx, dy
        noise = self.radius * self.randomness * 0.15
        return dx + random.gauss(0, noise), dy + random.gauss(0, noise)

    @abstractmethod
    def steps(self, max_steps: int = 500) -> Iterator[tuple[float, float]]:
        ...


class CircularPattern(MovementPattern):
    """Moves in a circle; radius and speed configurable."""

    def steps(self, max_steps: int = 500) -> Iterator[tuple[float, float]]:
        angle_step = (2 * math.pi / 60) * self.speed
        angle = 0.0
        for _ in range(max_steps):
            dx = self.radius * math.cos(angle)
            dy = self.radius * math.sin(angle)
            yield self._add_noise(dx, dy)
            angle += angle_step
            if angle >= 2 * math.pi:
                angle -= 2 * math.pi


class ZigZagPattern(MovementPattern):
    """Zig-zags horizontally across a field stripe."""

    def steps(self, max_steps: int = 500) -> Iterator[tuple[float, float]]:
        step_size = max(4, self.radius // 8)
        x = -self.radius
        direction = 1
        row = 0
        row_height = max(8, self.radius // 5)

        for _ in range(max_steps):
            dy = row * row_height - self.radius // 2
            yield self._add_noise(x, dy)
            x += step_size * direction
            if abs(x) >= self.radius:
                x = self.radius * direction * -1
                direction *= -1
                row = (row + 1) % (self.radius // row_height + 1)


class SpiralPattern(MovementPattern):
    """Inward/outward spiral."""

    def steps(self, max_steps: int = 500) -> Iterator[tuple[float, float]]:
        angle = 0.0
        r = 0.0
        expanding = True
        angle_step = 0.25 * self.speed
        r_step = 1.5 * self.speed

        for _ in range(max_steps):
            dx = r * math.cos(angle)
            dy = r * math.sin(angle)
            yield self._add_noise(dx, dy)
            angle += angle_step
            if expanding:
                r += r_step
                if r >= self.radius:
                    expanding = False
            else:
                r -= r_step
                if r <= 0:
                    expanding = True


class CornerRotationPattern(MovementPattern):
    """Cycles through the four corners of a bounding square."""

    def steps(self, max_steps: int = 500) -> Iterator[tuple[float, float]]:
        corners = [
            (-self.radius, -self.radius),
            (self.radius, -self.radius),
            (self.radius, self.radius),
            (-self.radius, self.radius),
        ]
        r = self.radius * 0.5
        idx = 0
        sub_steps = max(5, int(20 / self.speed))
        cx, cy = corners[0]

        for step in range(max_steps):
            if step % sub_steps == 0:
                idx = (idx + 1) % 4
                cx, cy = corners[idx]
            yield self._add_noise(
                cx + random.uniform(-r * 0.3, r * 0.3),
                cy + random.uniform(-r * 0.3, r * 0.3),
            )


class WaypointPattern(MovementPattern):
    """
    Follows a user-defined list of (dx, dy) waypoints in order, looping.
    Waypoints are stored in the profile as a list of [dx, dy] pairs.
    """

    def __init__(self, waypoints: list[list[float]], **kwargs):
        super().__init__(**kwargs)
        self._waypoints = waypoints if waypoints else [[0, 0]]

    def steps(self, max_steps: int = 500) -> Iterator[tuple[float, float]]:
        idx = 0
        for _ in range(max_steps):
            wp = self._waypoints[idx % len(self._waypoints)]
            yield self._add_noise(wp[0], wp[1])
            idx += 1


class PatternFactory:
    _registry = {
        "circular": CircularPattern,
        "zig-zag": ZigZagPattern,
        "zigzag": ZigZagPattern,
        "spiral": SpiralPattern,
        "corner": CornerRotationPattern,
        "corner_rotation": CornerRotationPattern,
        "waypoint": WaypointPattern,
    }

    @classmethod
    def create(cls, name: str, **kwargs) -> MovementPattern:
        key = name.lower().replace(" ", "_")
        klass = cls._registry.get(key, CircularPattern)
        return klass(**kwargs)

    @classmethod
    def available_patterns(cls) -> list[str]:
        return ["circular", "zig-zag", "spiral", "corner_rotation", "waypoint"]
