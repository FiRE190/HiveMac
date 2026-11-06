"""
Environment check: required packages and the two macOS permissions.
Permission checks are best effort; the wizard also tests them live.
"""
from __future__ import annotations

import importlib
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
    from setup import permissions
    return permissions.check().screen_capture


def check_accessibility() -> Optional[bool]:
    from setup import permissions
    return permissions.check().keys_ok


def print_report(s: EnvStatus) -> None:
    print(f"Python {s.python_version}")
    print("Packages: " + ("ok" if s.packages_ok else "missing " + ", ".join(s.missing_packages)))
    print(f"Screen Recording: {_fmt(s.screen_recording)}   Accessibility: {_fmt(s.accessibility)}")


def _fmt(v: Optional[bool]) -> str:
    return "granted" if v else ("denied" if v is False else "unknown")
