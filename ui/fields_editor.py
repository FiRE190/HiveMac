"""Fields tab. Each field is one short line (on, name, minutes, backpack %).
Everything else is under "more" and defaults to Natro's setting for that field."""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from movement.patterns import FIELDS, PATTERNS, SIZE_FACTORS
from profiles.profile_manager import get_profile_manager
from ui.widgets import Collapsible
from utils.logger import get_logger

log = get_logger(__name__)
_LOCATIONS = ["center", "upper left", "upper", "upper right", "left", "right", "lower left", "lower", "lower right"]
_D = "(default)"


def _num(text: str, default: float) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


class FieldRow(ctk.CTkFrame):
    def __init__(self, master, data: dict, on_remove: Callable[["FieldRow"], None]) -> None:
        super().__init__(master, corner_radius=8)
        d = dict(data)
        self._on_remove = on_remove
        self.v_enabled = ctk.BooleanVar(value=d.get("enabled", True))
        self.v_name = ctk.StringVar(value=d.get("name", "sunflower"))
        self.v_minutes = ctk.StringVar(value=str(d.get("minutes", 10)))
        self.v_backpack = ctk.StringVar(value=str(d.get("backpack_percent", 95)))
        self.v_pattern = ctk.StringVar(value=d.get("pattern") or _D)
        self.v_size = ctk.StringVar(value=str(d.get("size") or _D))
        self.v_width = ctk.StringVar(value=str(d.get("width") or ""))
        self.v_travel = ctk.StringVar(value=d.get("travel", "default"))
        self.v_ret = ctk.StringVar(value=d.get("return_method", "reset"))
        self.v_shift = ctk.BooleanVar(value=d.get("shift_lock", False))
        self.v_camera = ctk.StringVar(value=d.get("camera") or _D)
        self.v_turns = ctk.StringVar(value=str(d.get("turns") or ""))
        self.v_sprinkler = ctk.StringVar(value=d.get("sprinkler_location") or _D)
        self.v_distance = ctk.StringVar(value=str(d.get("sprinkler_distance") or ""))
        self.v_inv_fb = ctk.BooleanVar(value=d.get("invert_fb") is True)
        self.v_inv_lr = ctk.BooleanVar(value=d.get("invert_lr") is True)
        self._has_inv = "invert_fb" in d or "invert_lr" in d
        self._build()

    def _build(self) -> None:
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=6, pady=(6, 2))
        ctk.CTkCheckBox(top, text="", variable=self.v_enabled, width=24).pack(side="left")
        ctk.CTkComboBox(top, values=FIELDS, variable=self.v_name, width=140).pack(side="left", padx=2)
        ctk.CTkLabel(top, text="minutes").pack(side="left", padx=(8, 2))
        ctk.CTkEntry(top, textvariable=self.v_minutes, width=50).pack(side="left")
        ctk.CTkLabel(top, text="backpack %").pack(side="left", padx=(8, 2))
        ctk.CTkEntry(top, textvariable=self.v_backpack, width=50).pack(side="left")
        ctk.CTkButton(top, text="x", width=28, fg_color="#7f1d1d", command=lambda: self._on_remove(self)).pack(side="right")

        more = Collapsible(self, "more")
        more.pack(fill="x", padx=6, pady=(0, 4))
        b = more.body
        a = ctk.CTkFrame(b, fg_color="transparent")
        a.pack(fill="x", pady=2)
        ctk.CTkLabel(a, text="pattern").pack(side="left")
        ctk.CTkComboBox(a, values=[_D] + sorted(PATTERNS), variable=self.v_pattern, width=150).pack(side="left", padx=3)
        ctk.CTkLabel(a, text="size").pack(side="left")
        ctk.CTkComboBox(a, values=[_D] + list(SIZE_FACTORS), variable=self.v_size, width=90).pack(side="left", padx=3)
        ctk.CTkLabel(a, text="width").pack(side="left")
        ctk.CTkEntry(a, textvariable=self.v_width, width=44).pack(side="left", padx=3)
        c = ctk.CTkFrame(b, fg_color="transparent")
        c.pack(fill="x", pady=2)
        ctk.CTkLabel(c, text="travel").pack(side="left")
        ctk.CTkComboBox(c, values=["default", "walk", "cannon"], variable=self.v_travel, width=96).pack(side="left", padx=3)
        ctk.CTkLabel(c, text="return").pack(side="left")
        ctk.CTkComboBox(c, values=["reset", "walk"], variable=self.v_ret, width=80).pack(side="left", padx=3)
        ctk.CTkCheckBox(c, text="shift lock", variable=self.v_shift, width=24).pack(side="left", padx=6)
        e = ctk.CTkFrame(b, fg_color="transparent")
        e.pack(fill="x", pady=2)
        ctk.CTkLabel(e, text="camera").pack(side="left")
        ctk.CTkComboBox(e, values=[_D, "none", "left", "right"], variable=self.v_camera, width=96).pack(side="left", padx=3)
        ctk.CTkLabel(e, text="turns").pack(side="left")
        ctk.CTkEntry(e, textvariable=self.v_turns, width=40).pack(side="left", padx=3)
        f = ctk.CTkFrame(b, fg_color="transparent")
        f.pack(fill="x", pady=2)
        ctk.CTkLabel(f, text="sprinkler").pack(side="left")
        ctk.CTkComboBox(f, values=[_D] + _LOCATIONS, variable=self.v_sprinkler, width=120).pack(side="left", padx=3)
        ctk.CTkLabel(f, text="distance").pack(side="left")
        ctk.CTkEntry(f, textvariable=self.v_distance, width=40).pack(side="left", padx=3)
        g = ctk.CTkFrame(b, fg_color="transparent")
        g.pack(fill="x", pady=2)
        ctk.CTkCheckBox(g, text="invert forward/back", variable=self.v_inv_fb, width=24).pack(side="left", padx=4)
        ctk.CTkCheckBox(g, text="invert left/right", variable=self.v_inv_lr, width=24).pack(side="left", padx=4)

    def to_dict(self) -> dict:
        d: dict = {"name": self.v_name.get().strip().lower(), "enabled": self.v_enabled.get(),
                   "minutes": _num(self.v_minutes.get(), 10.0), "backpack_percent": int(_num(self.v_backpack.get(), 95)),
                   "travel": self.v_travel.get(), "return_method": self.v_ret.get(), "shift_lock": self.v_shift.get()}
        if self.v_pattern.get() != _D:
            d["pattern"] = self.v_pattern.get()
        if self.v_size.get() != _D:
            d["size"] = self.v_size.get()
        if self.v_width.get().strip():
            d["width"] = int(_num(self.v_width.get(), 1))
        if self.v_camera.get() != _D:
            d["camera"] = self.v_camera.get()
        if self.v_turns.get().strip():
            d["turns"] = int(_num(self.v_turns.get(), 1))
        if self.v_sprinkler.get() != _D:
            d["sprinkler_location"] = self.v_sprinkler.get()
        if self.v_distance.get().strip():
            d["sprinkler_distance"] = int(_num(self.v_distance.get(), 1))
        if self._has_inv or self.v_inv_fb.get() or self.v_inv_lr.get():
            d["invert_fb"] = self.v_inv_fb.get()
            d["invert_lr"] = self.v_inv_lr.get()
        return d


class FieldsEditor(ctk.CTkFrame):
    def __init__(self, master, on_profile_changed: Callable[[dict], None]) -> None:
        super().__init__(master, fg_color="transparent")
        self._pm = get_profile_manager()
        self._on_changed = on_profile_changed
        self._rows: list[FieldRow] = []
        self._profile: dict = {}
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(4, 2))
        self._profile_name = ctk.StringVar()
        self._combo = ctk.CTkComboBox(top, values=self._pm.list_profiles() or ["default"], variable=self._profile_name,
                                      width=150, command=lambda _v: self.load(self._profile_name.get()))
        self._combo.pack(side="left", padx=2)
        ctk.CTkButton(top, text="Save", width=56, fg_color="#1d4ed8", command=self.save).pack(side="left", padx=2)
        ctk.CTkButton(top, text="New", width=50, command=self._new).pack(side="left", padx=2)
        ctk.CTkButton(top, text="Delete", width=58, fg_color="#7f1d1d", command=self._delete).pack(side="left", padx=2)
        ctk.CTkButton(top, text="+ field", width=70, command=lambda: self._add_row({"name": "sunflower"})).pack(side="right", padx=2)
        self._list = ctk.CTkScrollableFrame(self, height=360)
        self._list.pack(fill="both", expand=True, pady=2)
        self.load_last()

    def load_last(self) -> None:
        self._set_profile(self._pm.load_last_used())

    def load(self, name: str) -> None:
        p = self._pm.load(name)
        if p:
            self._set_profile(p)

    def _set_profile(self, p: dict) -> None:
        self._profile = p
        self._profile_name.set(p.get("name", "default"))
        for r in self._rows:
            r.destroy()
        self._rows = []
        for f in p.get("fields", []):
            self._add_row(f)
        self._combo.configure(values=self._pm.list_profiles() or ["default"])
        self._on_changed(self.current())

    def _add_row(self, data: dict) -> None:
        row = FieldRow(self._list, data, self._remove_row)
        row.pack(fill="x", pady=3, padx=2)
        self._rows.append(row)

    def _remove_row(self, row: FieldRow) -> None:
        row.destroy()
        self._rows = [r for r in self._rows if r is not row]

    def current(self) -> dict:
        p = dict(self._profile)
        p["name"] = self._profile_name.get().strip() or "default"
        p["fields"] = [r.to_dict() for r in self._rows]
        return p

    def save(self) -> None:
        p = self.current()
        self._pm.save(p)
        self._profile = p
        self._combo.configure(values=self._pm.list_profiles())
        self._on_changed(p)
        log.info("Profile '%s' saved with %d fields", p["name"], len(p["fields"]))

    def _new(self) -> None:
        name = (ctk.CTkInputDialog(text="Profile name:", title="New profile").get_input() or "").strip()
        if name:
            self._set_profile(self._pm.create(name))

    def _delete(self) -> None:
        if self._pm.delete(self._profile_name.get()):
            self.load_last()

    def refresh_from_disk(self) -> None:
        self.load_last()
