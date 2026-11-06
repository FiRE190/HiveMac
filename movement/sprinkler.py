"""
Walk from the field arrival point to a start corner and place sprinklers,
ported from Natro's nm_setSprinkler. Distances are Natro's millisecond holds
at walk speed 18, expressed here as `hold` steps scaled to the player's speed
by the walker (Natro: factor 18 / MoveSpeedNum).
"""
from __future__ import annotations

from movement.paths import Step

# [length, width] in Natro milliseconds at distance 10 and speed 18
FIELD_DIMENSIONS: dict[str, tuple[int, int]] = {
    "sunflower": (1250, 2000), "dandelion": (2500, 1000), "mushroom": (1250, 1750),
    "blue flower": (2750, 750), "clover": (2000, 1500), "spider": (2000, 2000),
    "strawberry": (1500, 2000), "bamboo": (3000, 1250), "pineapple": (1750, 3000),
    "stump": (1500, 1500), "cactus": (1500, 2500), "pumpkin": (1500, 2500),
    "pine tree": (2500, 1750), "rose": (2500, 1500), "mountain top": (2250, 1500),
    "pepper": (1500, 2250), "coconut": (1500, 2250),
}

SPRINKLER_TYPES = ("none", "basic", "silver", "golden", "diamond", "supreme")
NATRO_SPRINKLER_SPEED = 18.0


def _ms_hold(keys, ms: float, speed: float) -> Step:
    return Step.hold(keys, ms / 1000.0 * NATRO_SPRINKLER_SPEED / max(1.0, speed))


def start_location_steps(field: str, location: str, distance: int, speed: float) -> list[Step]:
    """Move from the arrival point to the chosen start location ("upper left", "center", ...)."""
    dims = FIELD_DIMENSIONS.get(field.lower())
    if not dims or location.lower() == "center":
        return [Step.wait(1.0)] if location.lower() == "center" else []
    flen = dims[0] * distance / 10.0
    fwid = dims[1] * distance / 10.0
    loc = location.lower()
    out: list[Step] = []
    if "upper" in loc or "top" in loc:
        out.append(_ms_hold("w", flen, speed))
    elif "lower" in loc or "bottom" in loc:
        out.append(_ms_hold("s", flen, speed))
    if "left" in loc:
        out.append(_ms_hold("a", fwid, speed))
    elif "right" in loc:
        out.append(_ms_hold("d", fwid, speed))
    return out


def placement_steps(sprinkler_type: str, location: str, slot_key: str, speed: float) -> list[Step]:
    """Key sequence that drops the sprinklers for a type. Supreme and basic are a
    single press; multi sprinkler types jump and place at offsets like Natro."""
    t = sprinkler_type.lower()
    if t == "none":
        return []
    if t in ("supreme", "basic"):
        return [Step.tap(slot_key)]
    loc = location.lower()
    fb_back = "s" if "upper" in loc else "w"
    fb_fwd = "w" if "upper" in loc else "s"
    lr_in = "d" if "left" in loc else "a"

    def jump_place() -> list[Step]:
        return [Step.hold("space", 0.2), Step.tap(slot_key), Step.wait(0.5)]

    out = jump_place()
    if t in ("silver", "golden", "diamond"):
        out += [_ms_hold(fb_back, 1000, speed), Step.wait(0.5)] + jump_place()
    if t == "silver":
        out += [_ms_hold(fb_fwd, 1000, speed)]
    if t in ("golden", "diamond"):
        out += [_ms_hold(lr_in, 1000, speed), Step.wait(0.5)] + jump_place()
    if t == "golden":
        out += [_ms_hold([fb_fwd, "a" if "left" in loc else "d"], 1400, speed)]
    if t == "diamond":
        out += [_ms_hold(fb_fwd, 1000, speed), Step.wait(0.5)] + jump_place()
        out += [_ms_hold("a" if "left" in loc else "d", 1000, speed)]
    return out
