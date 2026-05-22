"""
Pre-start validation system.

Runs before the macro begins farming.  Checks every critical system
and returns a structured report.  The UI gates the Start button on
validation passing (or user explicitly overriding warnings).
"""
from dataclasses import dataclass, field
from typing import Optional

from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class ValidationItem:
    name:     str
    ok:       bool
    message:  str
    blocking: bool = True   # if True, prevents Start; if False, just a warning
    fix_hint: str  = ""


@dataclass
class ValidationReport:
    items: list[ValidationItem] = field(default_factory=list)

    @property
    def can_start(self) -> bool:
        return all(item.ok for item in self.items if item.blocking)

    @property
    def has_warnings(self) -> bool:
        return any(not item.ok for item in self.items if not item.blocking)

    @property
    def blocking_failures(self) -> list[ValidationItem]:
        return [i for i in self.items if not i.ok and i.blocking]

    @property
    def warnings(self) -> list[ValidationItem]:
        return [i for i in self.items if not i.ok and not i.blocking]


def run_validation(profile: dict) -> ValidationReport:
    report = ValidationReport()

    _check_roblox(report)
    _check_permissions(report)
    _check_ocr(report)
    _check_hive(report, profile)
    _check_backpack_region(report)
    _check_movement(report)
    _check_templates(report)

    passed  = sum(1 for i in report.items if i.ok)
    total   = len(report.items)
    log.info("Validation: %d/%d passed, can_start=%s", passed, total, report.can_start)

    return report


# ------------------------------------------------------------------ #
# Individual checks                                                    #
# ------------------------------------------------------------------ #

def _check_roblox(report: ValidationReport) -> None:
    from calibration.roblox_finder import is_roblox_running
    found = is_roblox_running()
    report.items.append(ValidationItem(
        name     = "Roblox window",
        ok       = found,
        message  = "Roblox detected in windowed mode" if found else "Roblox not detected",
        blocking = True,
        fix_hint = "Open Roblox and start Bee Swarm Simulator in windowed mode",
    ))


def _check_permissions(report: ValidationReport) -> None:
    from setup.env_checker import _check_screen_recording, _check_accessibility

    sr = _check_screen_recording()
    report.items.append(ValidationItem(
        name     = "Screen Recording permission",
        ok       = sr is not False,
        message  = "Screen Recording granted" if sr else "Screen Recording denied or unknown",
        blocking = True,
        fix_hint = "System Settings → Privacy & Security → Screen Recording → add Terminal/Python",
    ))

    ax = _check_accessibility()
    report.items.append(ValidationItem(
        name     = "Accessibility permission",
        ok       = ax is not False,
        message  = "Accessibility granted" if ax else "Accessibility denied or unknown",
        blocking = True,
        fix_hint = "System Settings → Privacy & Security → Accessibility → add Terminal/Python",
    ))


def _check_ocr(report: ValidationReport) -> None:
    try:
        import pytesseract
        import subprocess
        r = subprocess.run(["tesseract", "--version"], capture_output=True, timeout=4)
        ok = r.returncode == 0
    except Exception:
        ok = False

    report.items.append(ValidationItem(
        name     = "Tesseract OCR",
        ok       = ok,
        message  = "Tesseract available" if ok else "Tesseract not installed",
        blocking = False,   # macro can still run, just no backpack % detection
        fix_hint = "Run: brew install tesseract",
    ))


def _check_hive(report: ValidationReport, profile: dict) -> None:
    from calibration.relative_coords import resolve
    hive_pos = resolve("hive")
    hive_cfg  = profile.get("hive", {})
    has_hive  = hive_pos is not None or hive_cfg.get("detected", False)

    report.items.append(ValidationItem(
        name     = "Hive location",
        ok       = has_hive,
        message  = "Hive location recorded" if has_hive else "Hive not calibrated",
        blocking = True,
        fix_hint = "Open Calibration → click 'Detect Hive' while standing near your hive",
    ))


def _check_backpack_region(report: ValidationReport) -> None:
    from config.config_manager import get_config
    cfg    = get_config()
    region = cfg.get("screen.regions.backpack_pct", {})
    ok     = bool(region.get("width", 0) > 0)

    report.items.append(ValidationItem(
        name     = "Backpack % region",
        ok       = ok,
        message  = f"Region set ({region.get('width')}×{region.get('height')}px)" if ok
                   else "Backpack region not calibrated",
        blocking = False,
        fix_hint = "Open Calibration → 'Auto-Detect' or drag-select the backpack % area",
    ))


def _check_movement(report: ValidationReport) -> None:
    try:
        import pyautogui
        _ = pyautogui.position()
        ok = True
    except Exception:
        ok = False

    report.items.append(ValidationItem(
        name     = "Movement (pyautogui)",
        ok       = ok,
        message  = "Mouse control available" if ok else "pyautogui failed — check Accessibility",
        blocking = True,
        fix_hint = "Grant Accessibility permission and restart the macro",
    ))


def _check_templates(report: ValidationReport) -> None:
    from pathlib import Path
    templates_dir = Path(__file__).parent.parent / "templates"
    required      = ["hive_ui.png"]
    missing       = [t for t in required if not (templates_dir / t).exists()]
    ok            = len(missing) == 0

    report.items.append(ValidationItem(
        name     = "Required templates",
        ok       = ok,
        message  = "All required templates present" if ok
                   else f"Missing: {', '.join(missing)}",
        blocking = False,
        fix_hint = "Open Calibration → Templates tab → capture the missing templates",
    ))
