"""
Main control panel window (customtkinter, 480×800, dark theme).

Layout (top to bottom):
  1. Title bar
  2. Status pill + runtime timer
  3. Info grid: State / Field / Backpack / Task counts
  4. Control buttons: Start | Pause | Stop | Debug | Calibration
  5. Calibration checklist (collapsible, shows green/red status)
  6. Profile editor (collapsible)
  7. Log console

All UI updates happen via after() — never blocked by background threads.
"""
import time
import threading
from typing import Optional

import customtkinter as ctk

from state.state_manager import get_state
from state.fsm import IDLE, FARMING, PAUSED
from services.farming_service import FarmingService
from ui.profile_editor import ProfileEditor
from ui.log_console import LogConsole
from calibration.checklist import get_checklist
from utils.logger import get_logger

log = get_logger(__name__)

_STATE_COLORS = {
    "IDLE":               "#374151",
    "FARMING":            "#065f46",
    "RETURNING_TO_HIVE":  "#1e40af",
    "CONVERTING_POLLEN":  "#1e40af",
    "WEALTH_CLOCK":       "#78350f",
    "MOB_RUN":            "#7c2d12",
    "DEATH_RECOVERY":     "#7f1d1d",
    "PAUSED":             "#4b5563",
}


def _fmt_time(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


class MainWindow(ctk.CTk):
    def __init__(self, farming_service: FarmingService) -> None:
        super().__init__()
        self._svc = farming_service
        self._sm = get_state()
        self._profile_visible = True

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("BeeSwarm Local Macro")
        self.geometry("480x820")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._sm.subscribe(self._on_state_changed)
        self._start_ui_update_loop()
        self.after(800, self._maybe_launch_wizard)

    # ------------------------------------------------------------------ #
    # UI Construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        # ---- Title ----
        title_bar = ctk.CTkFrame(self, height=44, corner_radius=0)
        title_bar.pack(fill="x")
        ctk.CTkLabel(
            title_bar,
            text="BeeSwarm Local Macro",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(side="left", padx=14, pady=8)
        ctk.CTkLabel(
            title_bar,
            text="personal use only",
            font=ctk.CTkFont(size=10),
            text_color="#6b7280",
        ).pack(side="left", pady=8)

        # ---- Status + timer ----
        status_bar = ctk.CTkFrame(self, fg_color="transparent")
        status_bar.pack(fill="x", padx=10, pady=(6, 2))

        self._state_pill = ctk.CTkLabel(
            status_bar,
            text="  IDLE  ",
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=8,
            fg_color=_STATE_COLORS["IDLE"],
            width=120,
        )
        self._state_pill.pack(side="left")

        self._timer_label = ctk.CTkLabel(
            status_bar,
            text="00:00:00",
            font=ctk.CTkFont(family="Courier", size=13),
            text_color="#9ca3af",
        )
        self._timer_label.pack(side="right", padx=8)

        # ---- Info grid ----
        info = ctk.CTkFrame(self, corner_radius=8)
        info.pack(fill="x", padx=10, pady=4)

        def info_cell(parent, label: str, col: int) -> ctk.CTkLabel:
            ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=10), text_color="#9ca3af").grid(
                row=0, column=col, padx=12, pady=(6, 0), sticky="w"
            )
            val = ctk.CTkLabel(parent, text="—", font=ctk.CTkFont(size=13, weight="bold"))
            val.grid(row=1, column=col, padx=12, pady=(0, 6), sticky="w")
            return val

        self._field_val   = info_cell(info, "FIELD",   0)
        self._bp_val      = info_cell(info, "BACKPACK", 1)
        self._wc_val      = info_cell(info, "W.CLOCKS", 2)
        self._mob_val     = info_cell(info, "MOB RUNS", 3)

        for i in range(4):
            info.columnconfigure(i, weight=1)

        # ---- Control buttons ----
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=6)

        self._start_btn = ctk.CTkButton(
            btn_row, text="START", width=90, height=36,
            fg_color="#065f46", hover_color="#047857",
            font=ctk.CTkFont(weight="bold"),
            command=self._on_start,
        )
        self._start_btn.pack(side="left", padx=4)

        self._pause_btn = ctk.CTkButton(
            btn_row, text="PAUSE", width=90, height=36,
            fg_color="#78350f", hover_color="#92400e",
            font=ctk.CTkFont(weight="bold"),
            command=self._on_pause,
            state="disabled",
        )
        self._pause_btn.pack(side="left", padx=4)

        self._stop_btn = ctk.CTkButton(
            btn_row, text="STOP", width=90, height=36,
            fg_color="#7f1d1d", hover_color="#991b1b",
            font=ctk.CTkFont(weight="bold"),
            command=self._on_stop,
            state="disabled",
        )
        self._stop_btn.pack(side="left", padx=4)

        # Debug toggle
        self._debug_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(btn_row, text="Debug", variable=self._debug_var,
                        command=self._on_debug_toggle, width=70).pack(side="left", padx=8)

        # Calibration button
        ctk.CTkButton(
            btn_row, text="Calibrate", width=90, height=36,
            command=self._open_calibration,
        ).pack(side="right", padx=4)

        # ---- Calibration checklist (collapsible) ----
        checklist_header = ctk.CTkFrame(self, fg_color="transparent")
        checklist_header.pack(fill="x", padx=10, pady=(4, 0))

        self._checklist_toggle_btn = ctk.CTkButton(
            checklist_header, text="▼ Calibration Status", width=200, height=26,
            fg_color="transparent", hover_color="#374151", anchor="w",
            command=self._toggle_checklist,
        )
        self._checklist_toggle_btn.pack(side="left")

        self._wizard_btn = ctk.CTkButton(
            checklist_header, text="Run Setup Wizard", width=140, height=26,
            fg_color="#1d4ed8", hover_color="#1e40af",
            command=self._open_wizard,
        )
        self._wizard_btn.pack(side="right")

        self._checklist_frame = ctk.CTkFrame(self, corner_radius=6)
        self._checklist_frame.pack(fill="x", padx=10, pady=2)
        self._checklist_visible = True
        self._checklist_rows: list = []
        self._build_checklist()

        # ---- Profile editor (collapsible) ----
        profile_header = ctk.CTkFrame(self, fg_color="transparent")
        profile_header.pack(fill="x", padx=10, pady=(4, 0))

        self._profile_toggle_btn = ctk.CTkButton(
            profile_header, text="▼ Profile Settings", width=200, height=26,
            fg_color="transparent", hover_color="#374151", anchor="w",
            command=self._toggle_profile,
        )
        self._profile_toggle_btn.pack(side="left")

        self._profile_frame = ctk.CTkFrame(self)
        self._profile_frame.pack(fill="x", padx=10, pady=2)

        self._profile_editor = ProfileEditor(
            self._profile_frame,
            on_profile_loaded=self._on_profile_loaded,
        )
        self._profile_editor.pack(fill="x", padx=2, pady=2)

        # ---- Log console ----
        log_header = ctk.CTkFrame(self, fg_color="transparent")
        log_header.pack(fill="x", padx=10, pady=(4, 0))
        ctk.CTkLabel(log_header, text="Log", text_color="#6b7280", font=ctk.CTkFont(size=11)).pack(side="left")
        ctk.CTkButton(log_header, text="Clear", width=50, height=20,
                      command=lambda: self._log_console.clear()).pack(side="right")

        self._log_console = LogConsole(self)
        self._log_console.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        # Load last profile on startup
        self._profile_editor.load_last_profile()

    # ------------------------------------------------------------------ #
    # Button handlers                                                      #
    # ------------------------------------------------------------------ #

    def _on_start(self) -> None:
        profile = self._profile_editor.get_active_profile()
        self._svc.start(profile)
        self._update_button_states(running=True)
        log.info("UI: Start pressed (profile='%s')", profile.get("name"))

    def _on_pause(self) -> None:
        state = self._sm.current_state
        if state == PAUSED:
            self._svc.resume()
            self._pause_btn.configure(text="PAUSE")
        else:
            self._svc.pause()
            self._pause_btn.configure(text="RESUME")

    def _on_stop(self) -> None:
        self._svc.stop()
        self._update_button_states(running=False)
        self._pause_btn.configure(text="PAUSE")
        log.info("UI: Stop pressed")

    def _on_debug_toggle(self) -> None:
        enabled = self._debug_var.get()
        self._sm.set(debug_mode=enabled)
        import logging
        level = logging.DEBUG if enabled else logging.INFO
        import logging as _l
        _l.getLogger().setLevel(level)
        log.info("Debug mode: %s", "ON" if enabled else "OFF")

    def _open_calibration(self) -> None:
        from calibration.calibration_tool import CalibrationWindow
        CalibrationWindow(self)

    def _open_wizard(self) -> None:
        from calibration.setup_wizard import SetupWizard
        SetupWizard(self)

    # ------------------------------------------------------------------ #
    # Calibration checklist                                                #
    # ------------------------------------------------------------------ #

    def _build_checklist(self) -> None:
        for w in self._checklist_frame.winfo_children():
            w.destroy()
        self._checklist_rows = []

        items = get_checklist()
        for i, item in enumerate(items):
            row = ctk.CTkFrame(self._checklist_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=1)

            indicator = ctk.CTkLabel(
                row,
                text="●",
                font=ctk.CTkFont(size=12),
                text_color="#22c55e" if item.ok else "#ef4444",
                width=18,
            )
            indicator.pack(side="left")

            ctk.CTkLabel(
                row,
                text=item.label,
                font=ctk.CTkFont(size=11),
                anchor="w",
                width=220,
            ).pack(side="left", padx=4)

            ctk.CTkLabel(
                row,
                text=item.detail,
                font=ctk.CTkFont(size=10),
                text_color="#6b7280",
                anchor="w",
            ).pack(side="left")

            if not item.ok:
                fix_btn = ctk.CTkButton(
                    row, text="Fix", width=40, height=20,
                    fg_color="#374151", hover_color="#4b5563",
                    font=ctk.CTkFont(size=10),
                    command=lambda k=item.key, cat=item.category: self._fix_item(k, cat),
                )
                fix_btn.pack(side="right", padx=4)

            self._checklist_rows.append((item, row))

    def _fix_item(self, key: str, category: str) -> None:
        """Open wizard at the relevant step, or open calibration tool."""
        from calibration.setup_wizard import SetupWizard, _STEPS
        for i, step in enumerate(_STEPS):
            if step.get("key") == key:
                SetupWizard(self, start_step=i)
                return
        from calibration.calibration_tool import CalibrationWindow
        CalibrationWindow(self)

    def _toggle_checklist(self) -> None:
        if self._checklist_visible:
            self._checklist_frame.pack_forget()
            self._checklist_toggle_btn.configure(text="▶ Calibration Status")
        else:
            self._checklist_frame.pack(fill="x", padx=10, pady=2,
                                       before=self._profile_frame)
            self._checklist_toggle_btn.configure(text="▼ Calibration Status")
        self._checklist_visible = not self._checklist_visible

    def _refresh_checklist(self) -> None:
        self._build_checklist()

    def _toggle_profile(self) -> None:
        if self._profile_visible:
            self._profile_frame.pack_forget()
            self._profile_toggle_btn.configure(text="▶ Profile Settings")
        else:
            self._profile_frame.pack(fill="x", padx=10, pady=2, before=self._log_console)
            self._profile_toggle_btn.configure(text="▼ Profile Settings")
        self._profile_visible = not self._profile_visible

    def _maybe_launch_wizard(self) -> None:
        from calibration.setup_wizard import should_show_wizard, SetupWizard
        if should_show_wizard():
            log.info("Calibration incomplete — launching setup wizard")
            SetupWizard(self)

    def _on_profile_loaded(self, profile: dict) -> None:
        log.info("Profile loaded in UI: '%s'", profile.get("name"))

    # ------------------------------------------------------------------ #
    # UI update loop (runs in main thread via after())                    #
    # ------------------------------------------------------------------ #

    def _start_ui_update_loop(self) -> None:
        self._update_ui()
        self.after(5000, self._refresh_checklist_periodic)

    def _update_ui(self) -> None:
        snap = self._sm.snapshot()

        # State pill
        state = snap["current_state"]
        color = _STATE_COLORS.get(state, "#374151")
        self._state_pill.configure(text=f"  {state}  ", fg_color=color)

        # Timer
        self._timer_label.configure(text=_fmt_time(snap["runtime_seconds"]))

        # Info grid
        self._field_val.configure(text=snap["current_field"] or "—")
        self._bp_val.configure(text=f"{snap['backpack_pct']}%")
        self._wc_val.configure(text=str(snap["wealth_clock_count"]))
        self._mob_val.configure(text=str(snap["mob_run_count"]))

        self.after(500, self._update_ui)

    def _refresh_checklist_periodic(self) -> None:
        self._build_checklist()
        self.after(5000, self._refresh_checklist_periodic)

    def _on_state_changed(self) -> None:
        # Called from bg thread — schedule UI update on main thread
        self.after(0, self._sync_button_states)

    def _sync_button_states(self) -> None:
        state = self._sm.current_state
        running = state != IDLE
        self._update_button_states(running)

    def _update_button_states(self, running: bool) -> None:
        if running:
            self._start_btn.configure(state="disabled")
            self._pause_btn.configure(state="normal")
            self._stop_btn.configure(state="normal")
        else:
            self._start_btn.configure(state="normal")
            self._pause_btn.configure(state="disabled")
            self._stop_btn.configure(state="disabled")

    # ------------------------------------------------------------------ #
    # Close                                                                #
    # ------------------------------------------------------------------ #

    def _on_close(self) -> None:
        self._svc.stop()
        self._sm.unsubscribe(self._on_state_changed)
        self.destroy()
