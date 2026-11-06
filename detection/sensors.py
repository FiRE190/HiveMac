"""
The real Sensors: binds the calibrated layout to the screen capture and the pure
decoders in detection.hud. The macro loop only talks to the Sensors protocol in
macro.game, so tests use a fake and never touch this file.

Calibration lives in config under `hud`:
  backpack_pixel, health_pixel           RelPoint
  hive_prompt_region, hive_view_region   RelRegion
  hive_prompt_template, hive_view_template   PNG file names in templates/ (optional)
  hive_strip_region                      RelRegion, colour fallback for the hive view
  template_tolerance                     per channel tolerance, default 12
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from calibration.layout import RelPoint, RelRegion, WindowBounds
from detection import hud
from utils import appdirs
from utils.logger import get_logger

log = get_logger(__name__)


TEMPLATES_DIR = appdirs.templates_dir()


def load_template(name: str) -> Optional[np.ndarray]:
    path = TEMPLATES_DIR / name
    if not name or not path.exists():
        return None
    try:
        from PIL import Image
        with Image.open(path) as im:
            return np.asarray(im.convert("RGB"))
    except Exception as exc:
        log.warning("template %s unreadable: %s", name, exc)
        return None


class ScreenSensors:
    def __init__(self, capture, window_provider, hud_cfg: dict) -> None:
        """window_provider() -> WindowBounds or None."""
        self._cap = capture
        self._window = window_provider
        self._cfg = hud_cfg
        self._filter = hud.BackpackFilter(size=int(hud_cfg.get("backpack_filter_size", 6)))
        self._tolerance = int(hud_cfg.get("template_tolerance", 12))
        self._tpl_prompt = load_template(hud_cfg.get("hive_prompt_template", ""))
        self._tpl_view = load_template(hud_cfg.get("hive_view_template", ""))
        self._tpl_cannon = load_template(hud_cfg.get("cannon_prompt_template", ""))
        self._tpl_dead = load_template(hud_cfg.get("death_template", ""))
        self.last_backpack_rgb: Optional[tuple[int, int, int]] = None

    # -- helpers --------------------------------------------------------------
    def _bounds(self) -> Optional[WindowBounds]:
        w = self._window()
        return w if w and w.width > 100 and w.height > 100 else None

    def _point(self, key: str) -> Optional[tuple[int, int]]:
        w = self._bounds()
        d = self._cfg.get(key)
        if not w or not d:
            return None
        return RelPoint.from_dict(d).absolute(w)

    def _region(self, key: str) -> Optional[np.ndarray]:
        w = self._bounds()
        d = self._cfg.get(key)
        if not w or not d:
            return None
        return self._cap.grab(RelRegion.from_dict(d).absolute(w))

    def _template_in(self, region_key: str, template: Optional[np.ndarray]) -> Optional[bool]:
        """None when not configured, else whether the template is in the region."""
        if template is None:
            return None
        img = self._region(region_key)
        if img is None:
            return False
        return hud.find_template(img, template, self._tolerance, step=2) is not None

    # -- Sensors protocol -----------------------------------------------------
    def roblox_present(self) -> bool:
        return self._bounds() is not None

    def backpack_raw(self) -> Optional[int]:
        p = self._point("backpack_pixel")
        if not p:
            return None
        rgb = self._cap.pixel(*p)
        self.last_backpack_rgb = rgb
        if rgb is None:
            return None
        return hud.backpack_percent_from_rgb(*rgb)

    def backpack_percent(self) -> int:
        return self._filter.push(self.backpack_raw())

    def backpack_unreadable_streak(self) -> int:
        return self._filter.unreadable_streak

    def reset_backpack_filter(self) -> None:
        self._filter.reset()

    def health_grey(self) -> bool:
        p = self._point("health_pixel")
        if not p:
            return False
        rgb = self._cap.pixel(*p)
        return bool(rgb) and hud.is_grey(*rgb)

    def hive_prompt_visible(self) -> Optional[bool]:
        return self._template_in("hive_prompt_region", self._tpl_prompt)

    def hive_view_visible(self) -> Optional[bool]:
        r = self._template_in("hive_view_region", self._tpl_view)
        if r is not None:
            return r
        strip = self._region("hive_strip_region")
        if strip is None or not self._cfg.get("hive_strip_enabled", False):
            return None
        # Existance macro: white respawn pad or blue balloon colours in the bottom strip
        white = hud.count_hls_range(strip, (0, 40, 0), (40, 100, 30))
        blue = hud.count_hls_range(strip, (105, 55, 82), (120, 86, 100))
        return (white + blue) >= int(self._cfg.get("hive_strip_min_pixels", 40))

    def cannon_prompt_visible(self) -> Optional[bool]:
        return self._template_in("hive_prompt_region", self._tpl_cannon)

    def death_text_visible(self) -> Optional[bool]:
        return self._template_in("death_region", self._tpl_dead)
