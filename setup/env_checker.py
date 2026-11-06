"""
Environment check: required packages and the two macOS permissions.
Permission checks are best effort; the wizard also tests them live.
"""
from __future__ import annotations

import importlib
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

REQUIRED = {"customtkinter": "customtkinter", "numpy": "numpy", "mss": "mss", "pynput": "pynput", "PIL": "Pillow"}


@dataclass
class EnvStatus:
    python_version: str = ""
    missing_packages: list[str] = field(default_factory=list)
    screen_recording: Optional[bool] = None
    accessibility: Optional[bool] = None

    @property
    def packages_ok(self) -> bool:
        return not self.missing_packages


def check_all() -> EnvStatus:
    s = EnvStatus(python_version=sys.version.split()[0])
    for module, pkg in REQUIRED.items():
        try:
            importlib.import_module(module)
        except Exception:
            s.missing_packages.append(pkg)
    s.screen_recording = check_screen_recording()
    s.accessibility = check_accessibility()
    return s


def check_screen_recording() -> Optional[bool]:
    """A capture that comes back all black on a lit screen means no permission.
    Returns None when it cannot tell."""
    try:
        import mss
        import numpy as np
        with mss.mss() as sct:
            img = sct.grab({"left": 0, "top": 0, "width": 200, "height": 60})
            arr = np.frombuffer(img.bgra, dtype=np.uint8)
            return bool(arr.any())
    except Exception:
        return None


def check_accessibility() -> Optional[bool]:
    try:
        out = subprocess.run(["osascript", "-e", 'tell application "System Events" to return name of first process'],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            return True
        if "not allowed assistive access" in (out.stderr or "").lower() or "1002" in (out.stderr or ""):
            return False
        return None
    except Exception:
        return None


def print_report(s: EnvStatus) -> None:
    print(f"Python {s.python_version}")
    print("Packages: " + ("ok" if s.packages_ok else "missing " + ", ".join(s.missing_packages)))
    print(f"Screen Recording: {_fmt(s.screen_recording)}   Accessibility: {_fmt(s.accessibility)}")


def _fmt(v: Optional[bool]) -> str:
    return "granted" if v else ("denied" if v is False else "unknown")
