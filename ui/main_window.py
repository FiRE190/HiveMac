"""
Control panel: header with state and runtime, Start / Pause / Stop, and four
tabs: Fields, Settings, Calibrate, Log. The remote control link is shown in the
header so a phone can take over.
"""
from __future__ import annotations

import customtkinter as ctk

from state.fsm import ERROR, IDLE, PAUSED
from state.state_manager import get_state
from ui.calibrate_panel import CalibratePanel
from ui.fields_editor import FieldsEditor
from ui.log_console import LogConsole
from ui.settings_editor import SettingsEditor
from utils.logger import get_logger

log = get_logger(__name__)

_STATE_COLORS = {
    "IDLE": "#374151", "RESETTING": "#1e40af", "CONVERTING": "#5b21b6", "TRAVELING": "#0e7490",
    "GATHERING": "#065f46", "PAUSED": "#4b5563", "ERROR": "#7f1d1d",
}


def _fmt_time(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


class MainWindow(ctk.CTk):
    def __init__(self, service) -> None:
        super().__init__()
        self._svc = service
        self._sm = get_state()
        self._profile: dict = {}
        self._shown: dict = {}
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        from utils.version import app_version
        self.title(f"HiveMac {app_version()}")
        self.geometry("620x840")
        self.minsize(600, 700)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()
        self._sm.subscribe(self._on_state_changed)
        self._update()

    def _build(self) -> None:
        head = ctk.CTkFrame(self, corner_radius=0, height=44)
        head.pack(fill="x")
        ctk.CTkLabel(head, text="HiveMac", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=14, pady=8)
        self._timer = ctk.CTkLabel(head, text="00:00:00", font=ctk.CTkFont(family="Courier", size=13), text_color="#9ca3af")
        self._timer.pack(side="right", padx=12)
        self._pill = ctk.CTkLabel(head, text="  IDLE  ", corner_radius=8, fg_color=_STATE_COLORS["IDLE"],
                                  font=ctk.CTkFont(size=12, weight="bold"), width=110)
        self._pill.pack(side="right", padx=6)

        self._detail = ctk.CTkLabel(self, text="", anchor="w", text_color="#d1d5db")
        self._detail.pack(fill="x", padx=14, pady=(6, 0))

        info = ctk.CTkFrame(self, corner_radius=8)
        info.pack(fill="x", padx=10, pady=4)
        self._cells = {}
        for col, (key, label) in enumerate([("field", "FIELD"), ("backpack_pct", "BACKPACK"), ("cycles", "CYCLES"),
                                            ("converts", "CONVERTS"), ("deaths", "DEATHS")]):
            ctk.CTkLabel(info, text=label, font=ctk.CTkFont(size=10), text_color="#9ca3af").grid(row=0, column=col, padx=10, pady=(6, 0), sticky="w")
            v = ctk.CTkLabel(info, text="-", font=ctk.CTkFont(size=13, weight="bold"))
            v.grid(row=1, column=col, padx=10, pady=(0, 6), sticky="w")
            self._cells[key] = v
            info.columnconfigure(col, weight=1)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=10, pady=4)
        self._start = ctk.CTkButton(btns, text="START", width=100, height=36, fg_color="#065f46", hover_color="#047857",
                                    font=ctk.CTkFont(weight="bold"), command=self._on_start)
        self._start.pack(side="left", padx=4)
        self._pause = ctk.CTkButton(btns, text="PAUSE", width=100, height=36, fg_color="#78350f", hover_color="#92400e",
                                    font=ctk.CTkFont(weight="bold"), command=self._on_pause, state="disabled")
        self._pause.pack(side="left", padx=4)
        self._stop = ctk.CTkButton(btns, text="STOP", width=100, height=36, fg_color="#7f1d1d", hover_color="#991b1b",
                                   font=ctk.CTkFont(weight="bold"), command=self._on_stop, state="disabled")
        self._stop.pack(side="left", padx=4)
        ctk.CTkLabel(btns, text="F9 stops everything", text_color="#6b7280", font=ctk.CTkFont(size=11)).pack(side="right", padx=8)

        self._remote = ctk.CTkEntry(self, placeholder_text="remote control link", font=ctk.CTkFont(size=11))
        self._remote.pack(fill="x", padx=14, pady=(0, 4))

        self._tabs = ctk.CTkTabview(self)
        self._tabs.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        for name in ("Fields", "Settings", "Calibrate", "Log"):
            self._tabs.add(name)
        self._fields = FieldsEditor(self._tabs.tab("Fields"), on_profile_changed=self._on_profile_changed)
        self._fields.pack(fill="both", expand=True)
        self._settings = SettingsEditor(self._tabs.tab("Settings"))
        self._settings.pack(fill="both", expand=True)
        self._calib = CalibratePanel(self._tabs.tab("Calibrate"), self._svc)
        self._calib.pack(fill="both", expand=True)
        self._log = LogConsole(self._tabs.tab("Log"))
        self._log.pack(fill="both", expand=True)

        urls = self._sm.remote_urls
        if urls:
            self._remote.insert(0, "  |  ".join(urls))
        from calibration.calibrator import required_complete
        if not required_complete():
            self._tabs.set("Calibrate")

    # ---------------------------------------------------------------- handlers
    def _on_profile_changed(self, profile: dict) -> None:
        self._profile = profile

    def _on_start(self) -> None:
        from calibration.calibrator import required_complete
        if not required_complete():
            self._detail.configure(text="Press Detect Roblox on the Calibrate tab first.")
            self._tabs.set("Calibrate")
            return
        self._fields.save()
        try:
            self._svc.start(self._fields.current())
        except Exception as exc:
            self._detail.configure(text=str(exc))

    def _on_pause(self) -> None:
        if self._sm.current_state == PAUSED:
            self._svc.resume()
        else:
            self._svc.pause()

    def _on_stop(self) -> None:
        self._svc.stop()

    def _on_state_changed(self) -> None:
        self.after(0, self._sync_buttons)

    def _sync_buttons(self) -> None:
        state = self._sm.current_state
        running = state not in (IDLE, ERROR)
        self._start.configure(state="disabled" if running else "normal")
        self._pause.configure(state="normal" if running else "disabled", text="RESUME" if state == PAUSED else "PAUSE")
        self._stop.configure(state="normal" if running else "disabled")

    def _set(self, key: str, widget, **kw) -> None:
        """Configure a widget only when its value changed; redraws are the main idle cost."""
        if self._shown.get(key) != kw:
            self._shown[key] = kw
            widget.configure(**kw)

    def _update(self) -> None:
        snap = self._sm.snapshot()
        state = snap["state"]
        self._set("pill", self._pill, text=f"  {state}  ", fg_color=_STATE_COLORS.get(state, "#374151"))
        self._set("timer", self._timer, text=_fmt_time(snap["runtime_seconds"]))
        if snap["detail"] or self._shown.get("detail_had"):
            self._set("detail", self._detail, text=snap["detail"] or "")
            self._shown["detail_had"] = bool(snap["detail"])
        self._set("field", self._cells["field"], text=snap["field"] or "-")
        self._set("bp", self._cells["backpack_pct"], text=f"{snap['backpack_pct']}%")
        for k in ("cycles", "converts", "deaths"):
            self._set(k, self._cells[k], text=str(snap[k]))
        if snap["remote_urls"] and not self._remote.get():
            self._remote.insert(0, "  |  ".join(snap["remote_urls"]))
        self.after(1000, self._update)

    def _on_close(self) -> None:
        self._svc.stop()
        self._sm.unsubscribe(self._on_state_changed)
        self.destroy()
