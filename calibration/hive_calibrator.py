"""
Hive calibration system.

Workflow:
  1. User stands at their hive in Roblox
  2. Clicks "Detect Hive" in the calibration UI
  3. This module captures the screen, tries template matching for hive UI elements,
     and falls back to asking the user to click the hive manually
  4. The hive location is stored in relative coordinates per-profile

Hive data stored in profile:
  "hive": {
    "name":      "My Hive",
    "rel_x":     0.42,
    "rel_y":     0.31,
    "anchor":    "roblox_window",
    "detected":  true,
    "method":    "template" | "manual" | "proximity"
  }
"""
import time
import threading
from pathlib import Path
from typing import Optional, Callable

from calibration.roblox_finder import get_roblox_bounds, roblox_bounds_or_screen, focus_roblox
from calibration.relative_coords import save_relative, resolve
from detection.screen_capture import get_screen_capture
from detection.template_matcher import match_template, match_any
from utils.logger import get_logger

log = get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Templates that indicate the hive is visible / nearby
_HIVE_TEMPLATES = [
    "hive_ui.png",
    "hive_converting.png",
    "hive_collect_prompt.png",
]


class HiveDetectionResult:
    def __init__(self) -> None:
        self.found:      bool  = False
        self.method:     str   = ""
        self.rel_x:      float = 0.0
        self.rel_y:      float = 0.0
        self.abs_x:      int   = 0
        self.abs_y:      int   = 0
        self.confidence: float = 0.0
        self.message:    str   = ""


class HiveCalibrator:
    def __init__(
        self,
        profile: dict,
        progress_cb: Optional[Callable[[str, float], None]] = None,
    ) -> None:
        self._profile    = profile
        self._cb         = progress_cb or (lambda msg, conf: None)
        self._result     = HiveDetectionResult()
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------ #
    # Primary detection                                                    #
    # ------------------------------------------------------------------ #

    def detect(self) -> HiveDetectionResult:
        """
        Attempt automatic hive detection.  Returns result with found=True
        on success.  Caller should fall back to manual if found=False.
        """
        self._cb("Looking for Roblox window...", 0.0)
        bounds = get_roblox_bounds(force_refresh=True)

        if not bounds:
            self._result.message = "Roblox window not found. Open Roblox in windowed mode."
            return self._result

        self._cb("Scanning for hive UI elements...", 0.2)

        # Method 1: template match for hive UI prompt
        found = self._try_template_detection(bounds)
        if found:
            return self._result

        # Method 2: color-based hive structure detection
        self._cb("Scanning for hive structure colors...", 0.5)
        found = self._try_color_detection(bounds)
        if found:
            return self._result

        # Method 3: proximity — use current player position as hive location
        self._cb("Using player position as hive location...", 0.7)
        found = self._try_proximity_detection(bounds)
        if found:
            return self._result

        self._result.message = (
            "Auto-detection failed. Stand next to your hive and click "
            "'Manual — click on hive' instead."
        )
        return self._result

    # ------------------------------------------------------------------ #
    # Manual recording                                                     #
    # ------------------------------------------------------------------ #

    def record_manual(
        self,
        abs_x: int,
        abs_y: int,
        hive_name: str = "My Hive",
    ) -> HiveDetectionResult:
        """Record a manually-clicked hive coordinate."""
        entry = save_relative("hive", abs_x, abs_y)
        self._result.found      = True
        self._result.method     = "manual"
        self._result.rel_x      = entry["rel_x"]
        self._result.rel_y      = entry["rel_y"]
        self._result.abs_x      = abs_x
        self._result.abs_y      = abs_y
        self._result.confidence = 1.0
        self._result.message    = f"Hive recorded manually at ({abs_x}, {abs_y})"

        self._save_to_profile(hive_name, entry["rel_x"], entry["rel_y"], "manual")
        log.info("Hive recorded manually: %s", self._result.message)
        return self._result

    # ------------------------------------------------------------------ #
    # Verification                                                         #
    # ------------------------------------------------------------------ #

    def verify(self) -> tuple[bool, str]:
        """
        Check if the saved hive coordinate is still valid by navigating
        there and looking for the hive UI prompt.
        Returns (ok, message).
        """
        pos = resolve("hive")
        if pos is None:
            return False, "No hive coordinate saved"

        sc    = get_screen_capture()
        screen = sc.capture_full()
        if screen is None:
            return False, "Screen capture failed"

        found, _, conf = match_template(screen, "hive_ui.png", threshold=0.70)
        if found:
            return True, f"Hive UI detected (confidence={conf:.0%})"

        found, _, _ = match_template(screen, "hive_converting.png", threshold=0.65)
        if found:
            return True, "Hive conversion UI detected"

        return False, "Hive not visible from current position — navigate to hive and retry"

    # ------------------------------------------------------------------ #
    # Internal detection methods                                           #
    # ------------------------------------------------------------------ #

    def _try_template_detection(self, bounds: dict) -> bool:
        sc     = get_screen_capture()
        screen = sc.capture_full()
        if screen is None:
            return False

        existing_templates = [
            t for t in _HIVE_TEMPLATES
            if (_TEMPLATES_DIR / t).exists()
        ]
        if not existing_templates:
            return False

        found, name, loc, conf = match_any(screen, existing_templates, threshold=0.72)
        if found and loc:
            self._finalize(loc[0], loc[1], "template", conf)
            self._result.message = f"Hive detected via template '{name}' (conf={conf:.0%})"
            log.info("Hive template match: %s conf=%.2f", name, conf)
            return True

        return False

    def _try_color_detection(self, bounds: dict) -> bool:
        """
        Look for the distinctive yellow/amber honeycomb color of BSS hives.
        Searches within the Roblox window bounds.
        """
        try:
            import cv2
            sc     = get_screen_capture()
            screen = sc.capture_full()
            if screen is None:
                return False

            # Crop to Roblox window
            crop = screen[
                bounds["top"]:bounds["top"] + bounds["height"],
                bounds["left"]:bounds["left"] + bounds["width"],
            ]

            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            # Honeycomb amber: hue 15-35, high saturation, medium-high value
            lower = (15, 100, 100)
            upper = (35, 255, 255)
            mask  = cv2.inRange(hsv, lower, upper)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                return False

            # Largest amber blob is likely the hive
            largest = max(contours, key=cv2.contourArea)
            area    = cv2.contourArea(largest)
            if area < 500:
                return False

            M = cv2.moments(largest)
            if M["m00"] == 0:
                return False

            cx = int(M["m10"] / M["m00"]) + bounds["left"]
            cy = int(M["m01"] / M["m00"]) + bounds["top"]
            conf = min(1.0, area / 5000)

            self._finalize(cx, cy, "color", conf)
            self._result.message = f"Hive detected via color analysis (conf={conf:.0%})"
            log.info("Hive color detection: cx=%d cy=%d area=%.0f", cx, cy, area)
            return True

        except Exception as e:
            log.debug("Color hive detection error: %s", e)
            return False

    def _try_proximity_detection(self, bounds: dict) -> bool:
        """
        Use center of Roblox window as approximate hive location.
        Low confidence — user is assumed to be standing near hive.
        """
        cx = bounds["left"] + bounds["width"]  // 2
        cy = bounds["top"]  + bounds["height"] // 2
        self._finalize(cx, cy, "proximity", 0.35)
        self._result.message = "Hive location estimated from window center (low confidence)"
        return True

    def _finalize(self, abs_x: int, abs_y: int, method: str, confidence: float) -> None:
        entry = save_relative("hive", abs_x, abs_y)
        self._result.found      = True
        self._result.method     = method
        self._result.rel_x      = entry["rel_x"]
        self._result.rel_y      = entry["rel_y"]
        self._result.abs_x      = abs_x
        self._result.abs_y      = abs_y
        self._result.confidence = confidence
        self._save_to_profile("My Hive", entry["rel_x"], entry["rel_y"], method)

    def _save_to_profile(
        self, name: str, rel_x: float, rel_y: float, method: str
    ) -> None:
        self._profile["hive"] = {
            "name":     name,
            "rel_x":    rel_x,
            "rel_y":    rel_y,
            "anchor":   "roblox_window",
            "detected": True,
            "method":   method,
        }
