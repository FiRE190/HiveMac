"""
Automatic calibration orchestrator.

Runs a sequence of detection passes to minimize manual input:
  1. Find Roblox window → persist bounds
  2. Detect Retina scale factor
  3. Auto-detect backpack % UI region via OCR text search
  4. Detect screen resolution

Returns an AutoCalibResult with per-step success flags and confidence.
"""
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable

import numpy as np

from calibration.roblox_finder import get_roblox_bounds, roblox_bounds_or_screen
from detection.screen_capture import get_screen_capture
from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class AutoCalibResult:
    roblox_found:        bool = False
    roblox_bounds:       Optional[dict] = None
    scale_factor:        float = 1.0
    scale_detected:      bool = False
    backpack_region:     Optional[dict] = None
    backpack_confidence: float = 0.0
    notes:               list[str] = field(default_factory=list)

    @property
    def overall_confidence(self) -> float:
        scores = [
            1.0 if self.roblox_found  else 0.0,
            1.0 if self.scale_detected else 0.5,
            self.backpack_confidence,
        ]
        return round(sum(scores) / len(scores), 2)


class AutoCalibrator:
    def __init__(self, progress_cb: Optional[Callable[[str, int], None]] = None) -> None:
        """
        progress_cb(message, percent) called during calibration so a UI
        can display progress without blocking the main thread.
        """
        self._cb = progress_cb or (lambda msg, pct: None)

    def run(self) -> AutoCalibResult:
        result = AutoCalibResult()
        self._cb("Detecting Roblox window...", 10)
        self._detect_roblox(result)

        self._cb("Detecting display scale factor...", 30)
        self._detect_scale(result)

        self._cb("Scanning for backpack UI region...", 55)
        self._detect_backpack_region(result)

        self._cb("Calibration complete", 100)
        log.info(
            "AutoCalib done: roblox=%s scale=%.1f backpack_conf=%.2f",
            result.roblox_found, result.scale_factor, result.backpack_confidence,
        )
        return result

    # ------------------------------------------------------------------ #

    def _detect_roblox(self, result: AutoCalibResult) -> None:
        bounds = get_roblox_bounds(force_refresh=True)
        if bounds:
            result.roblox_found = True
            result.roblox_bounds = bounds
            log.info("Roblox window: %s", bounds)
        else:
            result.notes.append("Roblox not detected — open Roblox in windowed mode")

    def _detect_scale(self, result: AutoCalibResult) -> None:
        try:
            sc = get_screen_capture()
            # MSS physical pixels vs logical screen size
            import mss
            with mss.mss() as sct:
                m = sct.monitors[1]
                logical_w = m["width"]
                img = np.array(sct.grab(m))
                physical_w = img.shape[1]

            if physical_w > logical_w:
                scale = physical_w / logical_w
            else:
                scale = 1.0

            result.scale_factor = round(scale, 2)
            result.scale_detected = True

            # Persist
            from config.config_manager import get_config
            cfg = get_config()
            cfg.set("screen.scale_factor", scale)
            cfg.save()

            log.info("Scale factor detected: %.2f", scale)
        except Exception as e:
            result.notes.append(f"Scale detection failed: {e}")
            result.scale_factor = 2.0  # safe default for Retina

    def _detect_backpack_region(self, result: AutoCalibResult) -> None:
        """
        Scan the Roblox window for a region containing a '%' character
        that's likely to be the backpack percentage display.
        OCR-scan strips of the right half of the screen (typical BSS HUD location).
        """
        try:
            sc = get_screen_capture()
            bounds = roblox_bounds_or_screen()
            full = sc.capture_full()

            if full is None or full.size == 0:
                result.notes.append("Screen capture failed — check Screen Recording permission")
                return

            # Search top 25% of Roblox window (HUD area), right 50%
            win_left = bounds["left"]
            win_top  = bounds["top"]
            win_w    = bounds["width"]
            win_h    = bounds["height"]

            search_left   = win_left + win_w // 2
            search_top    = win_top
            search_width  = win_w // 2
            search_height = win_h // 4

            region_img = sc.capture_region({
                "left":   search_left,
                "top":    search_top,
                "width":  search_width,
                "height": search_height,
            })

            if region_img is None:
                return

            # OCR the region and look for a percentage pattern
            from ocr.ocr_manager import get_ocr
            import re
            ocr   = get_ocr()
            text  = ocr.read_region_image(region_img)
            match = re.search(r"(\d{1,3})\s*%", text)

            if match:
                # Found a %; do a finer scan to isolate the exact sub-region
                pct_value = int(match.group(1))
                log.info("Found '%%' in HUD scan (value=%d%%)", pct_value)

                # Use the full search strip as the region (good enough for OCR)
                region = {
                    "left":   search_left,
                    "top":    search_top,
                    "width":  search_width,
                    "height": min(60, search_height),
                }
                result.backpack_region    = region
                result.backpack_confidence = 0.75

                self._save_backpack_region(region)
                result.notes.append(f"Backpack region auto-detected (read: {pct_value}%)")
            else:
                result.notes.append(
                    "Backpack % not auto-detected — use 'Select Region' in the calibration tool"
                )

        except Exception as e:
            log.warning("Backpack auto-detect error: %s", e)
            result.notes.append(f"Backpack scan error: {e}")

    def _save_backpack_region(self, region: dict) -> None:
        from config.config_manager import get_config
        cfg = get_config()
        cfg.set("screen.regions.backpack_pct", region)
        cfg.save()


def run_auto_calibration(
    progress_cb: Optional[Callable[[str, int], None]] = None,
) -> AutoCalibResult:
    return AutoCalibrator(progress_cb).run()
