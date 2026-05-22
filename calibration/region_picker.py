"""
Drag-to-select OCR region picker.

Shows a fullscreen semi-transparent overlay. User clicks and drags to
draw a rectangle. On mouse-up the region is saved to config and a
preview with OCR test is shown.

Usage:
    picker = RegionPicker(parent_window, region_name="backpack_pct",
                          on_saved=callback)
    picker.show()
"""
import json
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional

from utils.logger import get_logger

log = get_logger(__name__)

_SETTINGS_FILE = Path(__file__).parent.parent / "config" / "settings.json"


def _load_settings() -> dict:
    if _SETTINGS_FILE.exists():
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_region(region_name: str, left: int, top: int, width: int, height: int) -> None:
    data = _load_settings()
    data.setdefault("screen", {}).setdefault("regions", {})[region_name] = {
        "left":   left,
        "top":    top,
        "width":  width,
        "height": height,
    }
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    log.info("OCR region '%s' saved: %dx%d @ (%d,%d)", region_name, width, height, left, top)


class RegionPicker:
    """
    Fullscreen transparent overlay for drawing a selection rectangle.
    Uses plain tkinter (not CTk) because CTk doesn't support per-window alpha.
    """

    def __init__(
        self,
        parent,
        region_name: str,
        on_saved: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self._parent      = parent
        self._region_name = region_name
        self._on_saved    = on_saved
        self._start_x     = 0
        self._start_y     = 0
        self._rect_id     = None
        self._overlay: Optional[tk.Toplevel] = None
        self._canvas: Optional[tk.Canvas]    = None

    def show(self) -> None:
        """Create and display the overlay."""
        self._overlay = tk.Toplevel(self._parent)
        self._overlay.title("")
        self._overlay.attributes("-fullscreen", True)
        self._overlay.attributes("-alpha", 0.35)
        self._overlay.attributes("-topmost", True)
        self._overlay.configure(bg="black")
        self._overlay.lift()

        self._canvas = tk.Canvas(
            self._overlay,
            bg="black",
            cursor="crosshair",
            highlightthickness=0,
        )
        self._canvas.pack(fill="both", expand=True)

        # Instruction label
        self._canvas.create_text(
            self._overlay.winfo_screenwidth() // 2,
            40,
            text=f"Click and drag to select the '{self._region_name}' region   |   ESC to cancel",
            fill="white",
            font=("Helvetica", 16, "bold"),
        )

        self._canvas.bind("<ButtonPress-1>",   self._on_press)
        self._canvas.bind("<B1-Motion>",       self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._overlay.bind("<Escape>",         lambda _: self._cancel())

    def _on_press(self, event: tk.Event) -> None:
        self._start_x = event.x
        self._start_y = event.y
        if self._rect_id:
            self._canvas.delete(self._rect_id)
        self._rect_id = self._canvas.create_rectangle(
            self._start_x, self._start_y,
            self._start_x, self._start_y,
            outline="#22c55e", width=2, dash=(4, 2),
        )

    def _on_drag(self, event: tk.Event) -> None:
        if self._rect_id:
            self._canvas.coords(
                self._rect_id,
                self._start_x, self._start_y,
                event.x, event.y,
            )

    def _on_release(self, event: tk.Event) -> None:
        x1 = min(self._start_x, event.x)
        y1 = min(self._start_y, event.y)
        x2 = max(self._start_x, event.x)
        y2 = max(self._start_y, event.y)

        width  = x2 - x1
        height = y2 - y1

        if width < 10 or height < 10:
            log.warning("RegionPicker: selection too small (%dx%d), ignoring", width, height)
            self._cancel()
            return

        self._overlay.destroy()
        self._overlay = None

        _save_region(self._region_name, x1, y1, width, height)
        region = {"left": x1, "top": y1, "width": width, "height": height}

        self._show_preview(region)

        if self._on_saved:
            try:
                self._on_saved(self._region_name, region)
            except Exception as e:
                log.error("RegionPicker on_saved callback error: %s", e)

    def _cancel(self) -> None:
        if self._overlay:
            self._overlay.destroy()
            self._overlay = None
        log.info("RegionPicker cancelled")

    def _show_preview(self, region: dict) -> None:
        """Capture the selected region, run OCR, and show a result popup."""
        import threading

        def _run():
            try:
                import mss
                import numpy as np
                with mss.mss() as sct:
                    sct_img = sct.grab(region)
                    img_array = np.array(sct_img)[:, :, :3]

                from ocr.ocr_manager import get_ocr
                ocr    = get_ocr()
                text   = ocr.read_region_image(img_array)
                number = ocr.read_number_from_image(img_array)

                self._parent.after(0, lambda: self._show_result_popup(text, number, region))
            except Exception as e:
                log.warning("RegionPicker preview error: %s", e)

        threading.Thread(target=_run, daemon=True).start()

    def _show_result_popup(self, text: str, number, region: dict) -> None:
        import customtkinter as ctk
        popup = ctk.CTkToplevel(self._parent)
        popup.title("Region saved — OCR preview")
        popup.geometry("360x180")
        popup.resizable(False, False)
        popup.attributes("-topmost", True)

        ctk.CTkLabel(
            popup,
            text=f"Region: {self._region_name}",
            font=ctk.CTkFont(weight="bold"),
        ).pack(pady=(14, 4))

        ctk.CTkLabel(popup, text=f"Size: {region['width']}×{region['height']} px").pack()
        ctk.CTkLabel(popup, text=f"OCR text:   '{text}'").pack(pady=2)
        ctk.CTkLabel(
            popup,
            text=f"Parsed number: {number}",
            text_color="#22c55e" if number is not None else "#ef4444",
        ).pack(pady=2)

        ctk.CTkButton(popup, text="Close", command=popup.destroy, width=80).pack(pady=10)
