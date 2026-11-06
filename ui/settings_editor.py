"""Settings tab: game numbers that are the same for every field, and remote control."""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from config.config_manager import get_config
from movement.sprinkler import SPRINKLER_TYPES
from utils.logger import get_logger

log = get_logger(__name__)

_FIELDS = [
    ("walk_speed", "Walk speed (in game settings panel, Natro default 28)", "entry"),
    ("hive_slot", "Hive slot 1 to 6 (1 is nearest the ramp)", "entry"),
    ("sprinkler_type", "Sprinkler type", ("combo", list(SPRINKLER_TYPES))),
    ("sprinkler_slot_key", "Sprinkler hotbar key", ("combo", ["1", "2", "3", "4", "5", "6", "7"])),
    ("travel", "Default travel", ("combo", ["walk", "cannon"])),
    ("window_mode", "Roblox window (windowed is simpler)", ("combo", ["windowed", "fullscreen"])),
    ("title_bar_height", "Title bar height in windowed mode (points)", "entry"),
    ("zoom_out_taps", "Zoom out taps after a reset", "entry"),
    ("reset_wait_s", "Wait after reset (s)", "entry"),
    ("death_extra_wait_s", "Extra wait after a death (s)", "entry"),
    ("convert_timeout_s", "Convert timeout (s)", "entry"),
    ("lost_screen_s", "Unreadable screen before reset (s)", "entry"),
    ("use_tool", "Hold mouse button while gathering", "check"),
]


class SettingsEditor(ctk.CTkFrame):
    def __init__(self, master, on_saved: Callable[[], None] | None = None) -> None:
        super().__init__(master, fg_color="transparent")
        self._on_saved = on_saved or (lambda: None)
        self._vars: dict[str, ctk.Variable] = {}
        cfg = get_config()
        game = cfg.get_section("game")
        grid = ctk.CTkScrollableFrame(self, height=420)
        grid.pack(fill="both", expand=True, pady=4)
        for i, (key, label, kind) in enumerate(_FIELDS):
            ctk.CTkLabel(grid, text=label, anchor="w").grid(row=i, column=0, sticky="w", padx=6, pady=4)
            val = game.get(key)
            if kind == "check":
                var = ctk.BooleanVar(value=bool(val))
                ctk.CTkCheckBox(grid, text="", variable=var, width=24).grid(row=i, column=1, sticky="w", padx=6)
            elif isinstance(kind, tuple):
                var = ctk.StringVar(value=str(val))
                ctk.CTkComboBox(grid, values=kind[1], variable=var, width=130).grid(row=i, column=1, sticky="w", padx=6)
            else:
                var = ctk.StringVar(value=str(val))
                ctk.CTkEntry(grid, textvariable=var, width=130).grid(row=i, column=1, sticky="w", padx=6)
            self._vars[key] = var
        row = len(_FIELDS)
        ctk.CTkLabel(grid, text="Remote control enabled (restart to apply)", anchor="w").grid(row=row, column=0, sticky="w", padx=6, pady=4)
        self._remote = ctk.BooleanVar(value=bool(cfg.get("remote.enabled", True)))
        ctk.CTkCheckBox(grid, text="", variable=self._remote, width=24).grid(row=row, column=1, sticky="w", padx=6)
        ctk.CTkLabel(grid, text="Remote port", anchor="w").grid(row=row + 1, column=0, sticky="w", padx=6, pady=4)
        self._port = ctk.StringVar(value=str(cfg.get("remote.port", 8765)))
        ctk.CTkEntry(grid, textvariable=self._port, width=130).grid(row=row + 1, column=1, sticky="w", padx=6)
        ctk.CTkButton(self, text="Save settings", fg_color="#1d4ed8", command=self.save).pack(pady=6)

    def save(self) -> None:
        cfg = get_config()
        for key, var in self._vars.items():
            v = var.get()
            if isinstance(v, str):
                v = v.strip()
                try:
                    v = int(v) if key in ("hive_slot", "zoom_out_taps", "title_bar_height") else float(v)
                except ValueError:
                    pass
            cfg.set(f"game.{key}", v)
        cfg.set("remote.enabled", bool(self._remote.get()))
        try:
            cfg.set("remote.port", int(self._port.get()))
        except ValueError:
            pass
        cfg.save()
        log.info("Settings saved")
        self._on_saved()
