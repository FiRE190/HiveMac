"""
Gather patterns, ported from Natro Macro's patterns/*.ahk.

Each pattern is a function (size, reps, facing_corner) -> list[Step] using the
abstract keys tc_fb, afc_fb, tc_lr, afc_lr (toward or away from the field
centre). Sizes: xs 0.25, s 0.5, m 1, l 1.5, xl 2. `reps` is Natro's "width".
"""
from __future__ import annotations

import math
from typing import Callable

from movement.paths import ABSTRACT_KEYS, Step

__all__ = ["ABSTRACT_KEYS", "PATTERNS", "FIELD_DEFAULTS", "FIELDS", "build_pattern", "size_factor"]

SIZE_FACTORS = {"xs": 0.25, "s": 0.5, "m": 1.0, "l": 1.5, "xl": 2.0}

TC_FB, AFC_FB, TC_LR, AFC_LR = "tc_fb", "afc_fb", "tc_lr", "afc_lr"


def size_factor(size: str | float) -> float:
    if isinstance(size, (int, float)):
        return float(size)
    return SIZE_FACTORS.get(str(size).lower(), 1.0)


def _w(keys, tiles) -> Step:
    return Step.walk(keys, tiles)


def snake(size: float, reps: int, facing_corner: int = 0) -> list[Step]:
    out = []
    for _ in range(reps):
        out += [_w(TC_LR, 11 * size), _w(TC_FB, 1), _w(AFC_LR, 11 * size), _w(TC_FB, 1)]
    for _ in range(reps):
        out += [_w(TC_LR, 11 * size), _w(AFC_FB, 1), _w(AFC_LR, 11 * size), _w(AFC_FB, 1)]
    return out


def lines(size: float, reps: int, facing_corner: int = 0) -> list[Step]:
    out = []
    for _ in range(reps):
        out += [_w(TC_FB, 11 * size), _w(TC_LR, 1), _w(AFC_FB, 11 * size), _w(TC_LR, 1)]
    for _ in range(reps):
        out += [_w(TC_FB, 11 * size), _w(AFC_LR, 1), _w(AFC_FB, 11 * size), _w(AFC_LR, 1)]
    return out


def squares(size: float, reps: int, facing_corner: int = 0) -> list[Step]:
    out = []
    for i in range(1, reps + 1):
        d = 5 * size + i
        out += [_w(TC_FB, d), _w(TC_LR, d), _w(AFC_FB, d), _w(AFC_LR, d)]
    return out


def diamonds(size: float, reps: int, facing_corner: int = 0) -> list[Step]:
    out = []
    for i in range(1, reps + 1):
        d = 5 * size + i
        out += [_w([TC_FB, TC_LR], d), _w([TC_FB, AFC_LR], d), _w([AFC_FB, AFC_LR], d), _w([AFC_FB, TC_LR], d)]
    return out


def slimline(size: float, reps: int, facing_corner: int = 0) -> list[Step]:
    return [_w(TC_LR, 4 * size + reps * 0.1 - 0.1), _w(AFC_LR, 8 * size), _w(TC_LR, 4 * size)]


def _xsnake_body(size: float, extra_tail: float) -> list[Step]:
    diag8 = math.sqrt(2 * (8 * size) ** 2)
    diag4 = math.sqrt(2 * (4 * size) ** 2)
    return [
        _w(TC_LR, 4 * size), _w(TC_FB, 2 * size), _w(AFC_LR, 8 * size), _w(TC_FB, 2 * size),
        _w(TC_LR, 8 * size), _w([AFC_LR, AFC_FB], diag8), _w(TC_LR, 8 * size), _w(TC_FB, 2 * size),
        _w(AFC_LR, 8 * size), _w(TC_FB, 6.7 * size + extra_tail),
    ], diag4


def xsnake(size: float, reps: int, facing_corner: int = 0) -> list[Step]:
    out: list[Step] = []
    for _ in range(reps):
        body, diag4 = _xsnake_body(size, 0.0)
        out += body
        out += [_w(TC_LR, 8 * size), _w(AFC_FB, 2 * size), _w(AFC_LR, 8 * size), _w(AFC_FB, 2 * size),
                _w(TC_LR, 8 * size), _w(AFC_FB, 2 * size), _w(AFC_LR, 8 * size), _w(AFC_FB, 3 * size),
                _w(TC_LR, 8 * size), _w([TC_FB, AFC_LR], diag4)]
    return out


def corner_x_snake(size: float, reps: int, facing_corner: int = 0) -> list[Step]:
    body, diag4 = _xsnake_body(size, 10.0)
    out = list(body)
    # corner alignment: push into the corner, back out, then the return half
    out += [_w(AFC_LR, 6 + reps), _w([AFC_LR, TC_FB], 3), _w(TC_LR, 2 + reps), _w(AFC_FB, 5)]
    out += [_w(TC_LR, 8 * size), _w(AFC_FB, 2 * size), _w(AFC_LR, 8 * size), _w(AFC_FB, 2 * size),
            _w(TC_LR, 8 * size), _w(AFC_FB, 2 * size), _w(AFC_LR, 8 * size), _w(AFC_FB, 3 * size),
            _w(TC_LR, 8 * size), _w([TC_FB, AFC_LR], diag4)]
    return out


def fork(size: float, reps: int, facing_corner: int = 0) -> list[Step]:
    gap = 0.75
    diag = gap * math.sqrt(2)
    length = (40 - gap * 16 - diag * 4) / 6
    out: list[Step] = []
    if facing_corner:
        out.append(_w("w", 1.5))
    out += [_w([TC_LR, AFC_FB], diag * 2), _w(TC_LR, ((reps - 1) * 4 + 2) * gap), _w([TC_LR, TC_FB], diag * 2)]
    for _ in range(reps):
        out += [_w(TC_FB, length * size), _w(AFC_LR, gap * 2), _w(AFC_FB, length * size), _w(AFC_LR, gap * 2)]
    out += [_w(TC_FB, length * size), _w(AFC_LR, gap * 2), _w(AFC_FB, length * size)]
    return out


def e_lol(size: float, reps: int, facing_corner: int = 0) -> list[Step]:
    spacing = 274 * 9 / 2000  # tiles between lines
    long = (1094 + 25 * facing_corner) * 9 / 2000 * size
    out = [_w(TC_LR, spacing * (reps * 2 + 1)), _w(AFC_FB, 5 * size)]
    for _ in range(reps):
        out += [_w(AFC_LR, spacing), _w(TC_FB, 5 * size), _w(AFC_LR, spacing), _w(AFC_FB, long)]
    out += [_w(TC_LR, spacing * (reps * 2 + 0.5)), _w(TC_FB, 5 * size)]
    for _ in range(reps):
        out += [_w(AFC_LR, spacing), _w(AFC_FB, long), _w(AFC_LR, spacing * 1.5), _w(TC_FB, 5 * size)]
    return out


def supercat(size: float, reps: int, facing_corner: int = 0) -> list[Step]:
    out: list[Step] = []
    for _ in range(reps):
        out += [_w(TC_LR, 1.25 * size), _w(TC_FB, 7 * size), _w(TC_LR, 1.25 * size), _w(AFC_FB, 6.66 * size),
                _w(TC_LR, 1.25 * size), _w(TC_FB, 7 * size), _w(TC_LR, 2 * size), _w(AFC_FB, 6.5 * size)]
    for _ in range(reps):
        out += [_w(AFC_LR, 1.25 * size), _w(TC_FB, 7 * size), _w(AFC_LR, 1 * size), _w(AFC_FB, 6.66 * size),
                _w(AFC_LR, 1.25 * size), _w(TC_FB, 7 * size), _w(AFC_LR, 1.25 * size), _w(AFC_FB, 6.5 * size)]
    return out


def stationary(size: float, reps: int, facing_corner: int = 0) -> list[Step]:
    return [Step.wait(10.0)]


PATTERNS: dict[str, Callable[[float, int, int], list[Step]]] = {
    "snake": snake,
    "lines": lines,
    "squares": squares,
    "diamonds": diamonds,
    "slimline": slimline,
    "xsnake": xsnake,
    "corner_x_snake": corner_x_snake,
    "fork": fork,
    "e_lol": e_lol,
    "supercat": supercat,
    "stationary": stationary,
}

# Natro's per field defaults (nm_importFieldDefaults), camera facing as the
# path leaves you. Sprinkler "upper left" etc. is relative to that facing.
FIELD_DEFAULTS: dict[str, dict] = {
    "sunflower":    dict(pattern="corner_x_snake", size="m", width=4, camera="none", turns=1, sprinkler="upper left", distance=8, invert_fb=False, invert_lr=True),
    "dandelion":    dict(pattern="corner_x_snake", size="m", width=6, camera="none", turns=1, sprinkler="upper left", distance=10, invert_fb=False, invert_lr=True),
    "mushroom":     dict(pattern="corner_x_snake", size="m", width=2, camera="none", turns=1, sprinkler="upper left", distance=8, invert_fb=False, invert_lr=True),
    "blue flower":  dict(pattern="corner_x_snake", size="m", width=7, camera="right", turns=2, sprinkler="center", distance=1, invert_fb=False, invert_lr=False),
    "clover":       dict(pattern="stationary", size="s", width=1, camera="none", turns=1, sprinkler="center", distance=1, invert_fb=False, invert_lr=False),
    "strawberry":   dict(pattern="corner_x_snake", size="m", width=4, camera="right", turns=2, sprinkler="upper left", distance=6, invert_fb=False, invert_lr=True),
    "spider":       dict(pattern="corner_x_snake", size="m", width=4, camera="none", turns=1, sprinkler="upper left", distance=8, invert_fb=False, invert_lr=True),
    "bamboo":       dict(pattern="corner_x_snake", size="m", width=6, camera="left", turns=2, sprinkler="upper left", distance=8, invert_fb=False, invert_lr=False),
    "pineapple":    dict(pattern="corner_x_snake", size="m", width=6, camera="left", turns=1, sprinkler="upper left", distance=8, invert_fb=False, invert_lr=True),
    "stump":        dict(pattern="squares", size="s", width=2, camera="right", turns=2, sprinkler="lower right", distance=3, invert_fb=False, invert_lr=False),
    "cactus":       dict(pattern="e_lol", size="s", width=3, camera="none", turns=1, sprinkler="center", distance=1, invert_fb=False, invert_lr=False),
    "pumpkin":      dict(pattern="corner_x_snake", size="s", width=3, camera="none", turns=1, sprinkler="upper right", distance=7, invert_fb=False, invert_lr=False),
    "pine tree":    dict(pattern="corner_x_snake", size="s", width=4, camera="left", turns=2, sprinkler="upper left", distance=8, invert_fb=False, invert_lr=False),
    "rose":         dict(pattern="corner_x_snake", size="m", width=3, camera="right", turns=2, sprinkler="lower right", distance=7, invert_fb=False, invert_lr=False),
    "pepper":       dict(pattern="e_lol", size="m", width=2, camera="left", turns=2, sprinkler="upper right", distance=3, invert_fb=False, invert_lr=False),
    "coconut":      dict(pattern="corner_x_snake", size="s", width=3, camera="right", turns=4, sprinkler="upper right", distance=5, invert_fb=False, invert_lr=False),
    "mountain top": dict(pattern="corner_x_snake", size="m", width=3, camera="none", turns=1, sprinkler="left", distance=3, invert_fb=True, invert_lr=False),
}

FIELDS = list(FIELD_DEFAULTS)


def build_pattern(name: str, size: str | float = "m", width: int = 1, facing_corner: int = 0) -> list[Step]:
    fn = PATTERNS.get(name.lower().replace(" ", "_").replace("-", "_"))
    if fn is None:
        raise KeyError(f"unknown pattern {name!r}; have {sorted(PATTERNS)}")
    return fn(size_factor(size), max(1, int(width)), int(facing_corner))
