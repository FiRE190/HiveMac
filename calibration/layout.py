"""
Where things are on screen, as fractions of the Roblox window.

Everything the macro reads is a point or a rectangle stored relative to the
window (0..1 of width and height) plus the UI y offset Natro calls offsetY.
Storing fractions means a moved or resized window still works, and the
wizard only has to record each spot once.

Natro's defaults (client coordinates, 1x scale) are kept as a starting guess:
  backpack pixel        x = width/2 + 62,  y = offsetY + 6
  health bar pixel      x = width - 75,    y = 36
  hive prompt region    x = width/2 - 200 .. +400, y = offsetY .. +125
  hive view region      bottom quarter of the window
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class WindowBounds:
    left: int
    top: int
    width: int
    height: int

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "WindowBounds":
        return WindowBounds(int(d["left"]), int(d["top"]), int(d["width"]), int(d["height"]))


@dataclass(frozen=True)
class RelPoint:
    fx: float   # 0..1 across the window
    fy: float

    def absolute(self, w: WindowBounds) -> tuple[int, int]:
        return w.left + int(round(self.fx * w.width)), w.top + int(round(self.fy * w.height))

    @staticmethod
    def from_absolute(x: int, y: int, w: WindowBounds) -> "RelPoint":
        return RelPoint((x - w.left) / max(1, w.width), (y - w.top) / max(1, w.height))

    def to_dict(self) -> dict:
        return {"fx": round(self.fx, 5), "fy": round(self.fy, 5)}

    @staticmethod
    def from_dict(d: dict) -> "RelPoint":
        return RelPoint(float(d["fx"]), float(d["fy"]))


@dataclass(frozen=True)
class RelRegion:
    fx: float
    fy: float
    fw: float
    fh: float

    def absolute(self, w: WindowBounds) -> dict:
        left = w.left + int(round(self.fx * w.width))
        top = w.top + int(round(self.fy * w.height))
        width = max(1, int(round(self.fw * w.width)))
        height = max(1, int(round(self.fh * w.height)))
        return {"left": left, "top": top, "width": width, "height": height}

    @staticmethod
    def from_absolute(region: dict, w: WindowBounds) -> "RelRegion":
        return RelRegion((region["left"] - w.left) / max(1, w.width), (region["top"] - w.top) / max(1, w.height),
                         region["width"] / max(1, w.width), region["height"] / max(1, w.height))

    def to_dict(self) -> dict:
        return {k: round(v, 5) for k, v in asdict(self).items()}

    @staticmethod
    def from_dict(d: dict) -> "RelRegion":
        return RelRegion(float(d["fx"]), float(d["fy"]), float(d["fw"]), float(d["fh"]))


def natro_defaults(w: WindowBounds, offset_y: int = 0) -> dict:
    """Starting guesses for the HUD spots, derived from Natro's constants. The
    wizard lets the user correct each one; these only seed the fields."""
    width, height = max(1, w.width), max(1, w.height)
    return {
        "backpack_pixel": RelPoint((width / 2 + 62) / width, (offset_y + 6) / height).to_dict(),
        "health_pixel": RelPoint((width - 75) / width, 36 / height).to_dict(),
        "hive_prompt_region": RelRegion((width / 2 - 200) / width, offset_y / height, 400 / width, 125 / height).to_dict(),
        "hive_view_region": RelRegion(0.0, 0.75, 1.0, 0.25).to_dict(),
        "hive_strip_region": RelRegion((width / 2 - 100) / width, (height - 10) / height, 200 / width, 10 / height).to_dict(),
        "mouse_park": RelPoint(350 / width, (offset_y + 100) / height).to_dict(),
    }


def clamp_region_to_window(region: dict, w: WindowBounds) -> dict:
    left = max(w.left, region["left"])
    top = max(w.top, region["top"])
    right = min(w.left + w.width, region["left"] + region["width"])
    bottom = min(w.top + w.height, region["top"] + region["height"])
    return {"left": left, "top": top, "width": max(1, right - left), "height": max(1, bottom - top)}
