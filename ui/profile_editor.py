"""
Profile editor widget: inline create/load/save/delete with a form
for all profile fields. Embedded inside the main window.
"""
from typing import Callable, Optional

import customtkinter as ctk

from profiles.profile_manager import get_profile_manager
from movement.patterns import PatternFactory
from detection.field_detector import KNOWN_FIELDS
from utils.logger import get_logger

log = get_logger(__name__)


class ProfileEditor(ctk.CTkFrame):
    def __init__(self, parent, on_profile_loaded: Optional[Callable[[dict], None]] = None, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self._pm = get_profile_manager()
        self._on_profile_loaded = on_profile_loaded
        self._current_profile: dict = {}
        self._build_ui()
        self._refresh_profile_list()

    # ------------------------------------------------------------------ #
    # UI Build                                                             #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        # ---- Profile selector row ----
        sel_row = ctk.CTkFrame(self, fg_color="transparent")
        sel_row.pack(fill="x", padx=6, pady=(6, 2))

        ctk.CTkLabel(sel_row, text="Profile:", width=60).pack(side="left")
        self._profile_var = ctk.StringVar(value="default")
        self._profile_menu = ctk.CTkOptionMenu(
            sel_row, values=["default"], variable=self._profile_var,
            command=self._on_profile_selected, width=150
        )
        self._profile_menu.pack(side="left", padx=4)

        ctk.CTkButton(sel_row, text="Load", width=60, command=self._load_profile).pack(side="left", padx=2)
        ctk.CTkButton(sel_row, text="Save", width=60, command=self._save_profile).pack(side="left", padx=2)

        ctk.CTkLabel(sel_row, text="New name:").pack(side="left", padx=(8, 2))
        self._new_name_entry = ctk.CTkEntry(sel_row, width=110, placeholder_text="profile name")
        self._new_name_entry.pack(side="left", padx=2)
        ctk.CTkButton(sel_row, text="Create", width=60, command=self._create_profile).pack(side="left", padx=2)
        ctk.CTkButton(sel_row, text="Delete", width=60, fg_color="#7f1d1d", hover_color="#991b1b",
                      command=self._delete_profile).pack(side="left", padx=2)

        # ---- Settings grid ----
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=6, pady=4)

        def row(label: str, r: int) -> ctk.CTkLabel:
            lbl = ctk.CTkLabel(grid, text=label, anchor="w", width=160)
            lbl.grid(row=r, column=0, sticky="w", padx=6, pady=2)
            return lbl

        # Field
        row("Target Field:", 0)
        self._field_var = ctk.StringVar(value=KNOWN_FIELDS[0])
        ctk.CTkOptionMenu(grid, values=KNOWN_FIELDS, variable=self._field_var, width=200).grid(
            row=0, column=1, sticky="w", padx=4, pady=2
        )

        # Backup field
        row("Backup Field:", 1)
        self._backup_var = ctk.StringVar(value=KNOWN_FIELDS[1])
        ctk.CTkOptionMenu(grid, values=KNOWN_FIELDS, variable=self._backup_var, width=200).grid(
            row=1, column=1, sticky="w", padx=4, pady=2
        )

        # Pattern
        row("Movement Pattern:", 2)
        patterns = PatternFactory.available_patterns()
        self._pattern_var = ctk.StringVar(value="circular")
        ctk.CTkOptionMenu(grid, values=patterns, variable=self._pattern_var, width=150).grid(
            row=2, column=1, sticky="w", padx=4, pady=2
        )

        # Backpack threshold
        row("Backpack Threshold %:", 3)
        self._threshold_entry = ctk.CTkEntry(grid, width=70)
        self._threshold_entry.insert(0, "90")
        self._threshold_entry.grid(row=3, column=1, sticky="w", padx=4, pady=2)

        # Randomness
        row("Randomness (0-1):", 4)
        self._randomness_entry = ctk.CTkEntry(grid, width=70)
        self._randomness_entry.insert(0, "0.3")
        self._randomness_entry.grid(row=4, column=1, sticky="w", padx=4, pady=2)

        # Toggles
        toggle_row = ctk.CTkFrame(self, fg_color="transparent")
        toggle_row.pack(fill="x", padx=6, pady=2)

        self._wealth_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(toggle_row, text="Wealth Clock", variable=self._wealth_var).pack(side="left", padx=8)

        self._mob_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(toggle_row, text="Mob Runs", variable=self._mob_var).pack(side="left", padx=8)

        self._brightness_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(toggle_row, text="Reduce Brightness", variable=self._brightness_var).pack(side="left", padx=8)

        self._status_label = ctk.CTkLabel(self, text="", text_color="gray", anchor="w")
        self._status_label.pack(fill="x", padx=8, pady=2)

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def _refresh_profile_list(self) -> None:
        profiles = self._pm.list_profiles() or []
        if "default" not in profiles:
            profiles = ["default"] + profiles
        self._profile_menu.configure(values=profiles)

    def _on_profile_selected(self, name: str) -> None:
        pass  # load on explicit button press only

    def _load_profile(self) -> None:
        name = self._profile_var.get()
        profile = self._pm.load(name)
        if profile:
            self._apply_profile(profile)
            self._status_label.configure(text=f"Loaded: {name}", text_color="green")
            if self._on_profile_loaded:
                self._on_profile_loaded(profile)

    def _save_profile(self) -> None:
        profile = self._collect_profile()
        self._pm.save(profile)
        self._current_profile = profile
        self._status_label.configure(text=f"Saved: {profile['name']}", text_color="green")
        self._refresh_profile_list()

    def _create_profile(self) -> None:
        name = self._new_name_entry.get().strip()
        if not name:
            self._status_label.configure(text="Enter a name", text_color="red")
            return
        profile = self._pm.create(name)
        self._apply_profile(profile)
        self._profile_var.set(name)
        self._refresh_profile_list()
        self._status_label.configure(text=f"Created: {name}", text_color="green")

    def _delete_profile(self) -> None:
        name = self._profile_var.get()
        if self._pm.delete(name):
            self._refresh_profile_list()
            self._profile_var.set("default")
            self._status_label.configure(text=f"Deleted: {name}", text_color="orange")

    # ------------------------------------------------------------------ #
    # Serialization                                                        #
    # ------------------------------------------------------------------ #

    def _apply_profile(self, profile: dict) -> None:
        self._current_profile = profile
        self._profile_var.set(profile.get("name", "default"))
        self._field_var.set(profile.get("target_field", KNOWN_FIELDS[0]))
        self._backup_var.set(profile.get("backup_field", KNOWN_FIELDS[1]))
        self._pattern_var.set(profile.get("movement_pattern", "circular"))

        self._threshold_entry.delete(0, "end")
        self._threshold_entry.insert(0, str(profile.get("backpack_threshold_pct", 90)))

        self._randomness_entry.delete(0, "end")
        self._randomness_entry.insert(0, str(profile.get("randomness", 0.3)))

        self._wealth_var.set(profile.get("wealth_clock_enabled", True))
        self._mob_var.set(profile.get("mob_run_enabled", True))
        self._brightness_var.set(profile.get("reduce_brightness", False))

    def _collect_profile(self) -> dict:
        p = dict(self._current_profile)
        p["name"] = self._profile_var.get()
        p["target_field"] = self._field_var.get()
        p["backup_field"] = self._backup_var.get()
        p["movement_pattern"] = self._pattern_var.get()
        try:
            p["backpack_threshold_pct"] = int(self._threshold_entry.get())
        except ValueError:
            p["backpack_threshold_pct"] = 90
        try:
            p["randomness"] = float(self._randomness_entry.get())
        except ValueError:
            p["randomness"] = 0.3
        p["wealth_clock_enabled"] = self._wealth_var.get()
        p["mob_run_enabled"] = self._mob_var.get()
        p["reduce_brightness"] = self._brightness_var.get()
        return p

    def get_active_profile(self) -> dict:
        return self._collect_profile()

    def load_last_profile(self) -> None:
        profile = self._pm.load_last_used()
        self._apply_profile(profile)
        if self._on_profile_loaded:
            self._on_profile_loaded(profile)
