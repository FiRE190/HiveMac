"""
Environment checker: verifies all dependencies and reports status.
Returns structured results used by both the CLI launcher and the GUI.
"""
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent

REQUIRED_IMPORTS = {
    "customtkinter": "customtkinter>=5.2.0",
    "cv2":           "opencv-python>=4.8.0",
    "pyautogui":     "pyautogui>=0.9.54",
    "mss":           "mss>=9.0.1",
    "PIL":           "Pillow>=10.0.0",
    "pytesseract":   "pytesseract>=0.3.10",
    "numpy":         "numpy>=1.24.0",
    "pynput":        "pynput>=1.7.6",
}


@dataclass
class EnvStatus:
    python_version: str = ""
    python_ok: bool = False
    missing_packages: list[str] = field(default_factory=list)
    packages_ok: bool = False
    tesseract_ok: bool = False
    tesseract_version: str = ""
    screen_recording_ok: Optional[bool] = None   # None = unknown
    accessibility_ok: Optional[bool] = None
    venv_active: bool = False
    all_ok: bool = False
    notes: list[str] = field(default_factory=list)


def check_all() -> EnvStatus:
    s = EnvStatus()

    # Python version
    v = sys.version_info
    s.python_version = f"{v.major}.{v.minor}.{v.micro}"
    s.python_ok = v.major == 3 and v.minor >= 9

    if not s.python_ok:
        s.notes.append(f"Python 3.9+ required (found {s.python_version})")

    # venv
    s.venv_active = sys.prefix != sys.base_prefix

    # Packages
    s.missing_packages = _check_packages()
    s.packages_ok = len(s.missing_packages) == 0

    # Tesseract
    s.tesseract_ok, s.tesseract_version = _check_tesseract()
    if not s.tesseract_ok:
        s.notes.append("Tesseract not found — install with: brew install tesseract")

    # Permissions (best-effort, non-blocking)
    s.screen_recording_ok = _check_screen_recording()
    s.accessibility_ok = _check_accessibility()

    if s.screen_recording_ok is False:
        s.notes.append("Screen Recording permission denied — grant in System Settings")
    if s.accessibility_ok is False:
        s.notes.append("Accessibility permission denied — grant in System Settings")

    s.all_ok = (
        s.python_ok
        and s.packages_ok
        and s.tesseract_ok
        and s.screen_recording_ok is not False
        and s.accessibility_ok is not False
    )

    return s


def _check_packages() -> list[str]:
    missing = []
    for module in REQUIRED_IMPORTS:
        try:
            __import__(module)
        except ImportError:
            missing.append(REQUIRED_IMPORTS[module])
    return missing


def _check_tesseract() -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["tesseract", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            version = r.stdout.splitlines()[0] if r.stdout else "unknown"
            return True, version
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False, ""


def _check_screen_recording() -> Optional[bool]:
    """
    Try a minimal screen capture. If the result is pure black (all zeros),
    Screen Recording permission is likely denied.
    Returns None if check could not be performed.
    """
    try:
        import mss
        import numpy as np
        with mss.mss() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            img = np.array(sct.grab(monitor))
        # A completely black frame almost certainly means permission denied
        if img.max() == 0:
            return False
        return True
    except Exception:
        return None


def _check_accessibility() -> Optional[bool]:
    """
    Try to read current mouse position via osascript.
    Returns None if check could not run, False if clearly denied.
    """
    try:
        r = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get position of mouse cursor'],
            capture_output=True, text=True, timeout=4,
        )
        if r.returncode == 0:
            return True
        # -1743 is the "not trusted" error code from AX API
        if "-1743" in r.stderr or "not allowed" in r.stderr.lower():
            return False
        return None
    except Exception:
        return None


def install_missing_packages(packages: list[str]) -> bool:
    """Attempt to pip-install the given package specs. Returns True on success."""
    if not packages:
        return True
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet"] + packages,
            timeout=120,
        )
        return result.returncode == 0
    except Exception:
        return False


def print_report(s: EnvStatus) -> None:
    tick = lambda ok: "✓" if ok else "✗"
    print(f"  [{tick(s.python_ok)}] Python {s.python_version}")
    print(f"  [{'✓' if s.venv_active else '·'}] Virtual environment {'active' if s.venv_active else 'not active (using system Python)'}")
    print(f"  [{tick(s.packages_ok)}] Python packages {'OK' if s.packages_ok else 'MISSING: ' + ', '.join(s.missing_packages)}")
    print(f"  [{tick(s.tesseract_ok)}] Tesseract OCR {s.tesseract_version or '(not found)'}")
    sr = {True: "granted", False: "DENIED", None: "unknown"}
    ax = {True: "granted", False: "DENIED", None: "unknown"}
    print(f"  [{'✓' if s.screen_recording_ok else '!'}] Screen Recording — {sr[s.screen_recording_ok]}")
    print(f"  [{'✓' if s.accessibility_ok else '!'}] Accessibility — {ax[s.accessibility_ok]}")
    for note in s.notes:
        print(f"  [!] {note}")
