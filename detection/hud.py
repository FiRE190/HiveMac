"""
Pure HUD decoding helpers. No screen access here, only numpy arrays and numbers,
so everything in this file is unit tested.

Colour order is RGB everywhere in this module. Capture code converts from the
BGRA that mss returns before calling in.
"""
from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Backpack bar: one pixel, decoded by colour into 5 percent steps.
# This is Natro Macro's ladder (submacros/background.ahk nm_backpackPercent),
# also used verbatim by the Existance macOS macro, so it is known to hold on
# macOS as long as the display colour profile is sRGB.
# ---------------------------------------------------------------------------


def rgb_to_int(r: int, g: int, b: int) -> int:
    return (int(r) << 16) | (int(g) << 8) | int(b)


def backpack_percent_from_rgb(r: int, g: int, b: int) -> Optional[int]:
    """Return 0..100 in steps of 5, or None when the colour is not a bar colour."""
    col = rgb_to_int(r, g, b)
    red = col & 0xFF0000
    gb = col & 0x00FFFF
    if red <= 0x690000:
        if red <= 0x4B0000:
            if red <= 0x420000:
                if red <= 0x410000 and gb <= 0x00FF80 and gb > 0x00FF86:
                    return 0
                if red > 0x410000 and gb <= 0x00FF80 and gb > 0x00FC85:
                    return 5
                return None
            if red <= 0x470000:
                if red <= 0x440000 and gb <= 0x00FE85 and gb > 0x00F984:
                    return 10
                if red > 0x440000 and gb <= 0x00FB84 and gb > 0x00F582:
                    return 15
                return None
            if gb <= 0x00F782 and gb > 0x00F080:
                return 20
            return None
        if red <= 0x5B0000:
            if red <= 0x4F0000 and gb <= 0x00F280 and gb > 0x00EA7D:
                return 25
            if red <= 0x550000 and gb <= 0x00EC7D and gb > 0x00E37A:
                return 30
            if red > 0x550000 and gb <= 0x00E57A and gb > 0x00DA76:
                return 35
            return None
        if red <= 0x620000 and gb <= 0x00DC76 and gb > 0x00D072:
            return 40
        if red > 0x620000 and gb <= 0x00D272 and gb > 0x00C66D:
            return 45
        return None
    if red <= 0x9C0000:
        if red <= 0x850000:
            if red <= 0x7B0000:
                if red <= 0x720000 and gb <= 0x00C86D and gb > 0x00BA68:
                    return 50
                if red > 0x720000 and gb <= 0x00BC68 and gb > 0x00AD62:
                    return 55
                return None
            if gb <= 0x00AF62 and gb > 0x009E5C:
                return 60
            return None
        if red <= 0x900000 and gb <= 0x00A05C and gb > 0x008F55:
            return 65
        if red > 0x900000 and gb <= 0x009155 and gb > 0x007E4E:
            return 70
        return None
    if red <= 0xC40000:
        if red <= 0xA90000 and gb <= 0x00804E and gb > 0x006C46:
            return 75
        if red <= 0xB60000 and gb <= 0x006E46 and gb > 0x005A3F:
            return 80
        if red > 0xB60000 and gb <= 0x005D3F and gb > 0x004637:
            return 85
        return None
    if red <= 0xD30000 and gb <= 0x004A37 and gb > 0x00322E:
        return 90
    if col == 0xF70017 or (red >= 0xE00000 and gb <= 0x002427 and gb > 0x001000):
        return 100
    if gb <= 0x00342E:
        return 95
    return None


class BackpackFilter:
    """Rolling mean of the last N readings, like Natro's 6 sample filter at 1 Hz.

    A None sample (no bar colour at the pixel) counts as 0, which is what an
    empty bar looks like, and bumps `unreadable_streak` so the loop can tell a
    long run of "nothing there" from a real empty bar.
    """

    def __init__(self, size: int = 6) -> None:
        self._values: deque[int] = deque(maxlen=size)
        self.unreadable_streak = 0

    def push(self, value: Optional[int]) -> int:
        if value is None:
            self.unreadable_streak += 1
            self._values.append(0)
        else:
            self.unreadable_streak = 0
            self._values.append(value)
        return self.value

    @property
    def value(self) -> int:
        if not self._values:
            return 0
        return int(round(sum(self._values) / len(self._values)))

    def reset(self) -> None:
        self._values.clear()
        self.unreadable_streak = 0


# ---------------------------------------------------------------------------
# Health bar: Natro reads one pixel of the bar and calls it "dead" when all
# three channels sit in the grey band 0x4D..0x83 (natro_macro.ahk nm_HealthBar).
# ---------------------------------------------------------------------------


def is_grey(r: int, g: int, b: int, low: int = 0x4D, high: int = 0x83) -> bool:
    return all(low <= int(c) <= high for c in (r, g, b))


# ---------------------------------------------------------------------------
# Colour matching on small arrays.
# ---------------------------------------------------------------------------


def count_colour(image: np.ndarray, rgb: tuple[int, int, int], tolerance: int) -> int:
    """Number of pixels within +-tolerance of rgb on every channel. image is (H, W, 3)."""
    target = np.asarray(rgb, dtype=np.int16)
    diff = np.abs(image[..., :3].astype(np.int16) - target)
    return int(np.count_nonzero(np.all(diff <= tolerance, axis=-1)))


def rgb_to_hls(image: np.ndarray) -> np.ndarray:
    """Vectorised RGB (0..255) to HLS with H in 0..360, L and S in 0..100. Returns float32 (H, W, 3)."""
    rgb = image[..., :3].astype(np.float32) / 255.0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = rgb.max(axis=-1)
    mn = rgb.min(axis=-1)
    light = (mx + mn) / 2.0
    delta = mx - mn
    sat = np.zeros_like(light)
    nonzero = delta > 1e-6
    denom = np.where(light <= 0.5, mx + mn, 2.0 - mx - mn)
    sat[nonzero] = delta[nonzero] / np.maximum(denom[nonzero], 1e-6)
    hue = np.zeros_like(light)
    rc = np.where(nonzero, (mx - r) / np.maximum(delta, 1e-6), 0)
    gc = np.where(nonzero, (mx - g) / np.maximum(delta, 1e-6), 0)
    bc = np.where(nonzero, (mx - b) / np.maximum(delta, 1e-6), 0)
    hue = np.where(mx == r, bc - gc, np.where(mx == g, 2.0 + rc - bc, 4.0 + gc - rc))
    hue = (hue / 6.0) % 1.0
    hue[~nonzero] = 0.0
    return np.stack([hue * 360.0, light * 100.0, sat * 100.0], axis=-1)


def count_hls_range(image: np.ndarray, low: tuple[float, float, float], high: tuple[float, float, float]) -> int:
    """Pixels whose HLS falls inside [low, high] (H 0..360, L 0..100, S 0..100)."""
    hls = rgb_to_hls(image)
    lo = np.asarray(low, dtype=np.float32)
    hi = np.asarray(high, dtype=np.float32)
    return int(np.count_nonzero(np.all((hls >= lo) & (hls <= hi), axis=-1)))


# ---------------------------------------------------------------------------
# Template search with a per channel tolerance, the way Natro's
# Gdip_ImageSearch "variation" works. Meant for small templates (tens of
# pixels) in small regions (hundreds of pixels). Pure numpy, no OpenCV.
# ---------------------------------------------------------------------------


def find_template(image: np.ndarray, template: np.ndarray, tolerance: int = 10,
                  step: int = 1) -> Optional[tuple[int, int]]:
    """Top left (x, y) of the first place where every sampled template pixel is
    within tolerance, or None. `step` samples every n-th template pixel to go
    faster on larger templates; 1 checks all of them.
    """
    img = image[..., :3].astype(np.int16)
    tpl = template[..., :3].astype(np.int16)
    th, tw = tpl.shape[:2]
    ih, iw = img.shape[:2]
    if th > ih or tw > iw or th == 0 or tw == 0:
        return None
    oh, ow = ih - th + 1, iw - tw + 1
    alive = np.ones((oh, ow), dtype=bool)
    # Check the corners and centre first; they eliminate most candidates early.
    order = [(0, 0), (th - 1, tw - 1), (th // 2, tw // 2), (0, tw - 1), (th - 1, 0)]
    seen = set(order)
    for y in range(0, th, step):
        for x in range(0, tw, step):
            if (y, x) not in seen:
                order.append((y, x))
    for y, x in order:
        window = img[y:y + oh, x:x + ow]
        diff = np.abs(window - tpl[y, x])
        alive &= np.all(diff <= tolerance, axis=-1)
        if not alive.any():
            return None
    ys, xs = np.nonzero(alive)
    return int(xs[0]), int(ys[0])
