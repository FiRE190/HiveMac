"""
Full screen overlays for calibration: click one point, or drag one rectangle.
Plain tkinter, because customtkinter cannot make a transparent window.
Results are absolute points on screen; callers convert them to window fractions.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

from utils.logger import get_logger

log = get_logger(__name__)


class _Overlay:
    def __init__(self, parent, text: str) -> None:
        self.win = tk.Toplevel(parent)
        self.win.title("")
        self.win.attributes("-fullscreen", True)
        self.win.attributes("-alpha", 0.3)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="black")
        self.canvas = tk.Canvas(self.win, bg="black", cursor="crosshair", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(self.win.winfo_screenwidth() // 2, 40, text=text + "   (Esc cancels)",
                                fill="white", font=("Helvetica", 16, "bold"))
        self.win.bind("<Escape>", lambda _e: self.close())
        self.win.lift()
        self.win.focus_force()

    def root_xy(self, event) -> tuple[int, int]:
        return int(event.x_root), int(event.y_root)

    def close(self) -> None:
        try:
            self.win.destroy()
        except Exception:
            pass


class PointPicker:
    def __init__(self, parent, text: str, on_picked: Callable[[int, int], None]) -> None:
        self._on_picked = on_picked
        self._ov = _Overlay(parent, text)
        self._ov.canvas.bind("<ButtonPress-1>", self._click)

    def _click(self, event) -> None:
        x, y = self._ov.root_xy(event)
        self._ov.close()
        try:
            self._on_picked(x, y)
        except Exception as exc:
            log.error("PointPicker callback: %s", exc)


class RegionPicker:
    def __init__(self, parent, text: str, on_picked: Callable[[dict], None], min_size: int = 6) -> None:
        self._on_picked = on_picked
        self._min = min_size
        self._ov = _Overlay(parent, text)
        self._start: Optional[tuple[int, int]] = None
        self._rect = None
        c = self._ov.canvas
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._drag)
        c.bind("<ButtonRelease-1>", self._release)

    def _press(self, event) -> None:
        self._start = (event.x, event.y)
        if self._rect:
            self._ov.canvas.delete(self._rect)
        self._rect = self._ov.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#22c55e", width=2)

    def _drag(self, event) -> None:
        if self._rect and self._start:
            self._ov.canvas.coords(self._rect, self._start[0], self._start[1], event.x, event.y)

    def _release(self, event) -> None:
        if not self._start:
            return
        sx, sy = self._start
        x1, y1, x2, y2 = min(sx, event.x), min(sy, event.y), max(sx, event.x), max(sy, event.y)
        # convert canvas coords to screen coords using the root offset of this event
        dx, dy = event.x_root - event.x, event.y_root - event.y
        region = {"left": x1 + dx, "top": y1 + dy, "width": x2 - x1, "height": y2 - y1}
        self._ov.close()
        if region["width"] < self._min or region["height"] < self._min:
            log.warning("selection too small, ignored")
            return
        try:
            self._on_picked(region)
        except Exception as exc:
            log.error("RegionPicker callback: %s", exc)
