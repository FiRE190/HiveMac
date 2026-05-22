"""
Auto-calibration control window.

Replaces the old CalibrationWindow with a streamlined panel that:
  • Detects Roblox window automatically
  • Runs full auto-calibration with progress bar
  • Has a "Detect Hive" button with visual confidence indicator
  • Shows pre-start validation report
  • Lets user select OCR region via drag-picker
  • Lets user record coordinates one-by-one
  • Has per-item status badges that update live
"""
import threading
import time
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from calibration.roblox_finder import get_roblox_bounds, focus_roblox, is_roblox_running
from calibration.auto_calibrator import run_auto_calibration, AutoCalibResult
from calibration.hive_calibrator import HiveCalibrator
from calibration.coordinate_recorder import CoordinateRecorder
from calibration.region_picker import RegionPicker
from calibration.validation import run_validation, ValidationReport
from utils.logger import get_logger

log = get_logger(__name__)

_CONF_COLOR = {
    "high":   "#22c55e",
    "medium": "#f59e0b",
    "low":    "#ef4444",
}


def _conf_color(conf: float) -> str:
    if conf >= 0.75:
        return _CONF_COLOR["high"]
    if conf >= 0.40:
        return _CONF_COLOR["medium"]
    return _CONF_COLOR["low"]


def _conf_label(conf: float) -> str:
    if conf >= 0.75:
        return f"High confidence ({conf:.0%})"
    if conf >= 0.40:
        return f"Medium confidence ({conf:.0%})"
    return f"Low confidence ({conf:.0%})"


class AutoCalibrationWindow(ctk.CTkToplevel):
    def __init__(self, parent, profile: dict) -> None:
        super().__init__(parent)
        self._profile  = profile
        self._recorder = CoordinateRecorder()

        self.title("Calibration")
        self.geometry("580x680")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self._build_ui()
        self.after(400, self._initial_check)

    # ------------------------------------------------------------------ #
    # UI Build                                                             #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        self._tabs = ctk.CTkTabview(self, width=560, height=640)
        self._tabs.pack(padx=10, pady=10, fill="both", expand=True)

        for tab in ["Auto-Detect", "Hive", "Coordinates", "OCR Region", "Validation"]:
            self._tabs.add(tab)

        self._build_auto_tab()
        self._build_hive_tab()
        self._build_coords_tab()
        self._build_ocr_tab()
        self._build_validation_tab()

    # ── Auto-Detect tab ────────────────────────────────────────────────

    def _build_auto_tab(self) -> None:
        tab = self._tabs.tab("Auto-Detect")

        ctk.CTkLabel(tab, text="Automatic Detection",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 4))
        ctk.CTkLabel(
            tab,
            text="Detects the Roblox window, display scale, and backpack UI\nautomatically. Run this first.",
            text_color="#9ca3af", wraplength=500,
        ).pack(pady=(0, 12))

        # Roblox status
        self._roblox_frame = ctk.CTkFrame(tab, corner_radius=6)
        self._roblox_frame.pack(fill="x", padx=8, pady=4)
        top = ctk.CTkFrame(self._roblox_frame, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 2))
        self._roblox_dot = ctk.CTkLabel(top, text="●", font=ctk.CTkFont(size=13), text_color="#6b7280")
        self._roblox_dot.pack(side="left")
        ctk.CTkLabel(top, text="Roblox Window", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=6)
        self._roblox_detail = ctk.CTkLabel(self._roblox_frame, text="Not checked", text_color="#6b7280", font=ctk.CTkFont(size=11))
        self._roblox_detail.pack(anchor="w", padx=10, pady=(0, 8))

        # Scale factor
        self._scale_frame = ctk.CTkFrame(tab, corner_radius=6)
        self._scale_frame.pack(fill="x", padx=8, pady=4)
        top2 = ctk.CTkFrame(self._scale_frame, fg_color="transparent")
        top2.pack(fill="x", padx=10, pady=(8, 2))
        self._scale_dot = ctk.CTkLabel(top2, text="●", font=ctk.CTkFont(size=13), text_color="#6b7280")
        self._scale_dot.pack(side="left")
        ctk.CTkLabel(top2, text="Display Scale (Retina)", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=6)
        self._scale_detail = ctk.CTkLabel(self._scale_frame, text="Not checked", text_color="#6b7280", font=ctk.CTkFont(size=11))
        self._scale_detail.pack(anchor="w", padx=10, pady=(0, 8))

        # Backpack
        self._bp_frame = ctk.CTkFrame(tab, corner_radius=6)
        self._bp_frame.pack(fill="x", padx=8, pady=4)
        top3 = ctk.CTkFrame(self._bp_frame, fg_color="transparent")
        top3.pack(fill="x", padx=10, pady=(8, 2))
        self._bp_dot = ctk.CTkLabel(top3, text="●", font=ctk.CTkFont(size=13), text_color="#6b7280")
        self._bp_dot.pack(side="left")
        ctk.CTkLabel(top3, text="Backpack % Region", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=6)
        self._bp_detail = ctk.CTkLabel(self._bp_frame, text="Not checked", text_color="#6b7280", font=ctk.CTkFont(size=11))
        self._bp_detail.pack(anchor="w", padx=10, pady=(0, 8))

        # Progress bar
        self._auto_progress = ctk.CTkProgressBar(tab, width=500)
        self._auto_progress.set(0)
        self._auto_progress.pack(pady=(12, 4))
        self._auto_status = ctk.CTkLabel(tab, text="", text_color="#9ca3af")
        self._auto_status.pack()

        # Buttons
        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.pack(pady=12)
        self._auto_btn = ctk.CTkButton(btn_row, text="Run Auto-Detection", width=180,
                                        command=self._run_auto_detect)
        self._auto_btn.pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Focus Roblox", width=120,
                      fg_color="#374151", hover_color="#4b5563",
                      command=self._focus_roblox).pack(side="left", padx=6)

    # ── Hive tab ───────────────────────────────────────────────────────

    def _build_hive_tab(self) -> None:
        tab = self._tabs.tab("Hive")

        ctk.CTkLabel(tab, text="Hive Detection",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 4))
        ctk.CTkLabel(
            tab,
            text="Stand near your hive in Roblox, then click Detect.\nIf auto-detection fails, use 'Record manually'.",
            text_color="#9ca3af", wraplength=500,
        ).pack(pady=(0, 12))

        # Status card
        self._hive_card = ctk.CTkFrame(tab, corner_radius=8)
        self._hive_card.pack(fill="x", padx=8, pady=4)

        card_top = ctk.CTkFrame(self._hive_card, fg_color="transparent")
        card_top.pack(fill="x", padx=12, pady=(10, 2))
        self._hive_dot = ctk.CTkLabel(card_top, text="●", font=ctk.CTkFont(size=16), text_color="#6b7280")
        self._hive_dot.pack(side="left")
        ctk.CTkLabel(card_top, text="Hive Location", font=ctk.CTkFont(weight="bold", size=13)).pack(side="left", padx=8)

        self._hive_conf_label = ctk.CTkLabel(self._hive_card, text="Not set", text_color="#6b7280")
        self._hive_conf_label.pack(anchor="w", padx=12, pady=(0, 4))
        self._hive_detail = ctk.CTkLabel(self._hive_card, text="", text_color="#9ca3af", font=ctk.CTkFont(size=11))
        self._hive_detail.pack(anchor="w", padx=12, pady=(0, 10))

        # Hive name
        name_row = ctk.CTkFrame(tab, fg_color="transparent")
        name_row.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(name_row, text="Hive name:", width=80).pack(side="left")
        self._hive_name_entry = ctk.CTkEntry(name_row, width=200, placeholder_text="My Hive")
        self._hive_name_entry.pack(side="left", padx=6)

        # Buttons
        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.pack(pady=8)

        self._detect_hive_btn = ctk.CTkButton(
            btn_row, text="Detect Hive (auto)", width=160,
            command=self._run_hive_detect,
        )
        self._detect_hive_btn.pack(side="left", padx=6)

        self._manual_hive_btn = ctk.CTkButton(
            btn_row, text="Record manually (click)", width=180,
            fg_color="#374151", hover_color="#4b5563",
            command=self._record_hive_manual,
        )
        self._manual_hive_btn.pack(side="left", padx=6)

        ctk.CTkButton(tab, text="Verify hive detection", width=200,
                      fg_color="#14532d", hover_color="#166534",
                      command=self._verify_hive).pack(pady=8)

        self._hive_verify_result = ctk.CTkLabel(tab, text="", text_color="#9ca3af")
        self._hive_verify_result.pack()

    # ── Coordinates tab ────────────────────────────────────────────────

    def _build_coords_tab(self) -> None:
        tab = self._tabs.tab("Coordinates")

        ctk.CTkLabel(tab, text="Record Coordinates",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 4))
        ctk.CTkLabel(tab, text="Type a name, click Record, then click anywhere in Roblox.",
                     text_color="#9ca3af").pack(pady=(0, 8))

        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(row, text="Name:", width=50).pack(side="left")
        self._coord_name = ctk.CTkEntry(row, width=180, placeholder_text="wealth_clock")
        self._coord_name.pack(side="left", padx=6)
        ctk.CTkButton(row, text="Record", width=80, command=self._record_coord).pack(side="left", padx=4)

        self._coord_status = ctk.CTkLabel(tab, text="", text_color="#9ca3af")
        self._coord_status.pack(pady=4)

        ctk.CTkLabel(tab, text="Saved coordinates:", anchor="w").pack(fill="x", padx=8, pady=(10, 2))
        self._coords_box = ctk.CTkTextbox(tab, height=280, state="disabled", font=("Courier", 11))
        self._coords_box.pack(fill="x", padx=8, pady=4)

        ctk.CTkButton(tab, text="Refresh", width=90, command=self._refresh_coords).pack(anchor="w", padx=8, pady=4)
        self._refresh_coords()

    # ── OCR Region tab ─────────────────────────────────────────────────

    def _build_ocr_tab(self) -> None:
        tab = self._tabs.tab("OCR Region")

        ctk.CTkLabel(tab, text="Backpack % Region",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 4))
        ctk.CTkLabel(
            tab,
            text="Select the screen area that shows your pollen percentage.\nDrag a rectangle over the number in the Roblox HUD.",
            text_color="#9ca3af", wraplength=500,
        ).pack(pady=(0, 12))

        self._ocr_status = ctk.CTkFrame(tab, corner_radius=6)
        self._ocr_status.pack(fill="x", padx=8, pady=4)
        self._ocr_status_label = ctk.CTkLabel(self._ocr_status, text="Not set", text_color="#6b7280")
        self._ocr_status_label.pack(padx=12, pady=10)
        self._update_ocr_status()

        ctk.CTkButton(tab, text="Drag to select region", height=36, width=220,
                      command=self._pick_backpack_region).pack(pady=12)

        ctk.CTkButton(tab, text="Test OCR now", width=160,
                      fg_color="#374151", hover_color="#4b5563",
                      command=self._test_ocr).pack(pady=4)

        self._ocr_result_label = ctk.CTkLabel(tab, text="", text_color="#9ca3af")
        self._ocr_result_label.pack(pady=4)

    # ── Validation tab ─────────────────────────────────────────────────

    def _build_validation_tab(self) -> None:
        tab = self._tabs.tab("Validation")

        ctk.CTkLabel(tab, text="Pre-Start Validation",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 4))
        ctk.CTkLabel(tab, text="Checks all systems before you press Start.",
                     text_color="#9ca3af").pack(pady=(0, 8))

        self._validation_frame = ctk.CTkScrollableFrame(tab, height=380)
        self._validation_frame.pack(fill="x", padx=8, pady=4)
        self._validation_summary = ctk.CTkLabel(tab, text="", font=ctk.CTkFont(weight="bold"))
        self._validation_summary.pack(pady=6)

        ctk.CTkButton(tab, text="Run Validation", width=150,
                      command=self._run_validation).pack(pady=4)

    # ------------------------------------------------------------------ #
    # Auto-detect actions                                                  #
    # ------------------------------------------------------------------ #

    def _initial_check(self) -> None:
        bounds = get_roblox_bounds()
        if bounds:
            self._set_roblox_status(True, bounds)
        else:
            self._roblox_dot.configure(text_color="#ef4444")
            self._roblox_detail.configure(text="Not detected — open Roblox in windowed mode")

    def _run_auto_detect(self) -> None:
        self._auto_btn.configure(state="disabled", text="Detecting...")

        def _run():
            def _progress(msg: str, pct: int) -> None:
                self.after(0, lambda: self._auto_status.configure(text=msg))
                self.after(0, lambda: self._auto_progress.set(pct / 100))

            result = run_auto_calibration(_progress)
            self.after(0, lambda: self._apply_auto_result(result))

        threading.Thread(target=_run, daemon=True).start()

    def _apply_auto_result(self, r: AutoCalibResult) -> None:
        self._auto_btn.configure(state="normal", text="Run Auto-Detection")

        self._set_roblox_status(r.roblox_found, r.roblox_bounds)

        # Scale
        color = _conf_color(1.0 if r.scale_detected else 0.0)
        self._scale_dot.configure(text_color=color)
        self._scale_detail.configure(
            text=f"Scale factor: {r.scale_factor}× {'(detected)' if r.scale_detected else '(default)'}",
        )

        # Backpack
        bp_color = _conf_color(r.backpack_confidence)
        self._bp_dot.configure(text_color=bp_color)
        if r.backpack_region:
            self._bp_detail.configure(
                text=f"Region: {r.backpack_region['width']}×{r.backpack_region['height']}px — {_conf_label(r.backpack_confidence)}",
            )
        else:
            self._bp_detail.configure(text="Not detected — use OCR Region tab to select manually")

        self._update_ocr_status()

        notes_text = "  " + "\n  ".join(r.notes) if r.notes else "  All checks passed"
        self._auto_status.configure(text=f"Done — confidence {r.overall_confidence:.0%}\n{notes_text}")

    def _set_roblox_status(self, found: bool, bounds: Optional[dict]) -> None:
        color = "#22c55e" if found else "#ef4444"
        self._roblox_dot.configure(text_color=color)
        if found and bounds:
            self._roblox_detail.configure(
                text=f"Found: {bounds['width']}×{bounds['height']} at ({bounds['left']}, {bounds['top']})",
            )
        else:
            self._roblox_detail.configure(text="Not detected")

    def _focus_roblox(self) -> None:
        focus_roblox()

    # ------------------------------------------------------------------ #
    # Hive actions                                                         #
    # ------------------------------------------------------------------ #

    def _run_hive_detect(self) -> None:
        self._detect_hive_btn.configure(state="disabled", text="Detecting...")

        def _run():
            def _cb(msg: str, conf: float) -> None:
                self.after(0, lambda: self._hive_conf_label.configure(text=msg))

            cal    = HiveCalibrator(self._profile, progress_cb=_cb)
            result = cal.detect()
            self.after(0, lambda: self._apply_hive_result(result))

        threading.Thread(target=_run, daemon=True).start()

    def _record_hive_manual(self) -> None:
        self._manual_hive_btn.configure(state="disabled", text="Click on hive in Roblox...")
        name = self._hive_name_entry.get().strip() or "My Hive"

        def _on_click(coord_name: str, x: int, y: int) -> None:
            cal    = HiveCalibrator(self._profile)
            result = cal.record_manual(x, y, name)
            self.after(0, lambda: self._apply_hive_result(result))
            self.after(0, lambda: self._manual_hive_btn.configure(state="normal", text="Record manually (click)"))

        self._recorder.start_recording("hive", on_saved=_on_click)

    def _apply_hive_result(self, result) -> None:
        self._detect_hive_btn.configure(state="normal", text="Detect Hive (auto)")
        color = _conf_color(result.confidence)
        self._hive_dot.configure(text_color=color)
        self._hive_conf_label.configure(
            text=_conf_label(result.confidence) if result.found else "Not detected",
            text_color=color,
        )
        self._hive_detail.configure(
            text=f"Method: {result.method} | {result.message}",
        )

    def _verify_hive(self) -> None:
        cal  = HiveCalibrator(self._profile)
        ok, msg = cal.verify()
        color = "#22c55e" if ok else "#ef4444"
        self._hive_verify_result.configure(text=msg, text_color=color)

    # ------------------------------------------------------------------ #
    # Coordinate actions                                                   #
    # ------------------------------------------------------------------ #

    def _record_coord(self) -> None:
        name = self._coord_name.get().strip()
        if not name:
            self._coord_status.configure(text="Enter a name first", text_color="#ef4444")
            return
        self._coord_status.configure(text=f"Click anywhere in Roblox to save '{name}'...", text_color="#f59e0b")

        def _on_saved(n: str, x: int, y: int) -> None:
            self.after(0, lambda: self._coord_status.configure(
                text=f"✓ Saved '{n}' = ({x}, {y})", text_color="#22c55e"
            ))
            self.after(0, self._refresh_coords)

        self._recorder.start_recording(name, on_saved=_on_saved)

    def _refresh_coords(self) -> None:
        from calibration.relative_coords import list_coordinates
        coords = list_coordinates()
        self._coords_box.configure(state="normal")
        self._coords_box.delete("1.0", "end")
        for name, val in sorted(coords.items()):
            if "rel_x" in val:
                line = f"  {name:28s}  rel=({val['rel_x']:.3f}, {val['rel_y']:.3f})\n"
            else:
                line = f"  {name:28s}  abs=({val.get('x','?')}, {val.get('y','?')})\n"
            self._coords_box.insert("end", line)
        self._coords_box.configure(state="disabled")

    # ------------------------------------------------------------------ #
    # OCR region actions                                                   #
    # ------------------------------------------------------------------ #

    def _pick_backpack_region(self) -> None:
        def _on_saved(name: str, region: dict) -> None:
            self.after(0, self._update_ocr_status)

        RegionPicker(self, "backpack_pct", on_saved=_on_saved).show()

    def _update_ocr_status(self) -> None:
        from config.config_manager import get_config
        cfg    = get_config()
        cfg.load()
        region = cfg.get("screen.regions.backpack_pct", {})
        if region.get("width", 0) > 0:
            text  = f"Set: {region['width']}×{region['height']}px at ({region['left']}, {region['top']})"
            color = "#22c55e"
        else:
            text  = "Not set — drag to select the backpack % area"
            color = "#ef4444"
        self._ocr_status_label.configure(text=text, text_color=color)

    def _test_ocr(self) -> None:
        def _run():
            try:
                from ocr.ocr_manager import get_ocr
                ocr  = get_ocr()
                text = ocr.read_region("backpack_pct")
                num  = ocr.read_number("backpack_pct")
                self.after(0, lambda: self._ocr_result_label.configure(
                    text=f"OCR text: '{text}'  |  Parsed: {num}%",
                    text_color="#22c55e" if num is not None else "#f59e0b",
                ))
            except Exception as e:
                self.after(0, lambda: self._ocr_result_label.configure(
                    text=f"OCR error: {e}", text_color="#ef4444"
                ))

        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------ #
    # Validation actions                                                   #
    # ------------------------------------------------------------------ #

    def _run_validation(self) -> None:
        for w in self._validation_frame.winfo_children():
            w.destroy()

        report = run_validation(self._profile)
        for item in report.items:
            row = ctk.CTkFrame(self._validation_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)

            dot_color = "#22c55e" if item.ok else ("#ef4444" if item.blocking else "#f59e0b")
            ctk.CTkLabel(row, text="●", text_color=dot_color, font=ctk.CTkFont(size=12), width=18).pack(side="left")
            ctk.CTkLabel(row, text=item.name, width=200, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=item.message, text_color="#9ca3af",
                         font=ctk.CTkFont(size=11), anchor="w").pack(side="left")

            if not item.ok and item.fix_hint:
                hint_row = ctk.CTkFrame(self._validation_frame, fg_color="transparent")
                hint_row.pack(fill="x", padx=20)
                ctk.CTkLabel(hint_row, text=f"→ {item.fix_hint}",
                             text_color="#6b7280", font=ctk.CTkFont(size=10), anchor="w").pack(side="left")

        if report.can_start:
            summary = "✓ All checks passed — ready to start"
            color   = "#22c55e"
        else:
            count   = len(report.blocking_failures)
            summary = f"✗ {count} blocking issue(s) must be resolved before starting"
            color   = "#ef4444"

        self._validation_summary.configure(text=summary, text_color=color)

    def destroy(self) -> None:
        self._recorder.stop()
        super().destroy()
