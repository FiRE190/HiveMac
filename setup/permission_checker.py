"""
macOS permission detection and guided remediation.

Screen Recording and Accessibility cannot be granted programmatically —
the user must do it manually. This module detects the current state,
opens the correct System Settings pane, and provides exact instructions.
"""
import subprocess
import sys
import threading
import time
from typing import Optional

from utils.logger import get_logger

log = get_logger(__name__)

_SCREEN_RECORDING_PREF = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
)
_ACCESSIBILITY_PREF = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
)


class PermissionStatus:
    def __init__(self) -> None:
        self.screen_recording: Optional[bool] = None
        self.accessibility: Optional[bool] = None
        self._lock = threading.Lock()

    def recheck(self) -> None:
        from setup.env_checker import _check_screen_recording, _check_accessibility
        with self._lock:
            self.screen_recording = _check_screen_recording()
            self.accessibility = _check_accessibility()

    @property
    def all_granted(self) -> bool:
        return self.screen_recording is True and self.accessibility is True

    @property
    def any_denied(self) -> bool:
        return self.screen_recording is False or self.accessibility is False


_status_instance: Optional[PermissionStatus] = None


def get_permission_status() -> PermissionStatus:
    global _status_instance
    if _status_instance is None:
        _status_instance = PermissionStatus()
        _status_instance.recheck()
    return _status_instance


def open_screen_recording_settings() -> None:
    subprocess.Popen(["open", _SCREEN_RECORDING_PREF])
    log.info("Opened Screen Recording settings")


def open_accessibility_settings() -> None:
    subprocess.Popen(["open", _ACCESSIBILITY_PREF])
    log.info("Opened Accessibility settings")


def open_privacy_settings() -> None:
    subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security"])


def show_permission_guide_window(parent) -> None:
    """
    Show a blocking permission guide window.  Polls permissions every 2s
    and closes automatically when both are granted.
    """
    import customtkinter as ctk

    win = ctk.CTkToplevel(parent)
    win.title("Required Permissions")
    win.geometry("500x420")
    win.resizable(False, False)
    win.attributes("-topmost", True)
    win.grab_set()  # modal

    ctk.CTkLabel(
        win,
        text="macOS Permissions Required",
        font=ctk.CTkFont(size=16, weight="bold"),
    ).pack(pady=(20, 6))

    ctk.CTkLabel(
        win,
        text="The macro needs two permissions to see and control Roblox.\nThese must be granted manually — macOS requires user approval.",
        wraplength=440,
        justify="center",
        text_color="#9ca3af",
    ).pack(pady=(0, 16))

    # ── Screen Recording ──────────────────────────────────────────────
    sr_frame = ctk.CTkFrame(win, corner_radius=8)
    sr_frame.pack(fill="x", padx=20, pady=4)

    sr_top = ctk.CTkFrame(sr_frame, fg_color="transparent")
    sr_top.pack(fill="x", padx=12, pady=(10, 4))

    sr_dot = ctk.CTkLabel(sr_top, text="●", font=ctk.CTkFont(size=14), width=20)
    sr_dot.pack(side="left")
    ctk.CTkLabel(sr_top, text="Screen Recording", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=6)

    ctk.CTkLabel(
        sr_frame,
        text="System Settings → Privacy & Security → Screen Recording\nAdd Terminal and Python — toggle both ON",
        text_color="#9ca3af", font=ctk.CTkFont(size=11), justify="left",
    ).pack(anchor="w", padx=12, pady=(0, 6))

    ctk.CTkButton(
        sr_frame, text="Open Screen Recording Settings", height=28,
        command=open_screen_recording_settings,
    ).pack(padx=12, pady=(0, 10))

    # ── Accessibility ─────────────────────────────────────────────────
    ax_frame = ctk.CTkFrame(win, corner_radius=8)
    ax_frame.pack(fill="x", padx=20, pady=4)

    ax_top = ctk.CTkFrame(ax_frame, fg_color="transparent")
    ax_top.pack(fill="x", padx=12, pady=(10, 4))

    ax_dot = ctk.CTkLabel(ax_top, text="●", font=ctk.CTkFont(size=14), width=20)
    ax_dot.pack(side="left")
    ctk.CTkLabel(ax_top, text="Accessibility", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=6)

    ctk.CTkLabel(
        ax_frame,
        text="System Settings → Privacy & Security → Accessibility\nAdd Terminal and Python — toggle both ON",
        text_color="#9ca3af", font=ctk.CTkFont(size=11), justify="left",
    ).pack(anchor="w", padx=12, pady=(0, 6))

    ctk.CTkButton(
        ax_frame, text="Open Accessibility Settings", height=28,
        command=open_accessibility_settings,
    ).pack(padx=12, pady=(0, 10))

    # ── Status + polling ──────────────────────────────────────────────
    status_label = ctk.CTkLabel(win, text="Checking permissions...", text_color="#9ca3af")
    status_label.pack(pady=(12, 4))

    skip_btn = ctk.CTkButton(
        win, text="Continue anyway (not recommended)", width=220, height=28,
        fg_color="transparent", hover_color="#374151", text_color="#6b7280",
        command=win.destroy,
    )
    skip_btn.pack(pady=4)

    ps = get_permission_status()

    def _tick():
        if not win.winfo_exists():
            return
        ps.recheck()
        sr_color = "#22c55e" if ps.screen_recording else ("#ef4444" if ps.screen_recording is False else "#f59e0b")
        ax_color = "#22c55e" if ps.accessibility else ("#ef4444" if ps.accessibility is False else "#f59e0b")
        sr_dot.configure(text_color=sr_color)
        ax_dot.configure(text_color=ax_color)

        if ps.all_granted:
            status_label.configure(text="✓ Both permissions granted — you're good to go!", text_color="#22c55e")
            win.after(1200, win.destroy)
        else:
            missing = []
            if not ps.screen_recording:
                missing.append("Screen Recording")
            if not ps.accessibility:
                missing.append("Accessibility")
            status_label.configure(text=f"Waiting for: {', '.join(missing)}", text_color="#f59e0b")
            win.after(2000, _tick)

    win.after(500, _tick)
