"""
Calibrate tab, kept short:
  1. Detect Roblox (also fills in Natro's default spots), then live readings check it.
  Natro's default walks for every field are built in; nothing to do for them.
  Adjust (collapsed): re-pick a reading that looks wrong.
  Record your own walk (collapsed, optional): overrides the built in one.
"""
from __future__ import annotations

import threading

import customtkinter as ctk

from calibration import calibrator
from calibration.layout import WindowBounds
from calibration.recorder import KeyRecorder, events_to_steps
from calibration.region_picker import PointPicker, RegionPicker
from config.config_manager import get_config
from movement.paths import USER_PATHS_DIR, PathFile, field_slug, find_path_file, list_fields_with_paths
from movement.patterns import FIELDS
from ui.widgets import Collapsible
from utils.logger import get_logger

log = get_logger(__name__)


class CalibratePanel(ctk.CTkFrame):
    def __init__(self, master, service) -> None:
        super().__init__(master, fg_color="transparent")
        self._svc = service
        self._window: WindowBounds | None = None
        self._recorder: KeyRecorder | None = None
        self._sensors = None
        self._live = False
        self._build()
        self.refresh_status()

    def _build(self) -> None:
        box = ctk.CTkScrollableFrame(self, height=520)
        box.pack(fill="both", expand=True, pady=4)

        # 1. detect
        s1 = ctk.CTkFrame(box, corner_radius=8)
        s1.pack(fill="x", padx=4, pady=4)
        self._dot = ctk.CTkLabel(s1, text="●", text_color="#ef4444", width=18)
        self._dot.pack(side="left", padx=(8, 2), pady=10)
        ctk.CTkLabel(s1, text="1. Open Roblox in a window, then", anchor="w").pack(side="left", padx=4)
        ctk.CTkButton(s1, text="Detect Roblox", width=130, fg_color="#1d4ed8", command=self._detect).pack(side="right", padx=8)

        # permissions
        self._perm_label = ctk.CTkLabel(box, text="", justify="left", anchor="w", wraplength=520, font=ctk.CTkFont(size=12))
        self._perm_label.pack(fill="x", padx=8, pady=(2, 0))
        self._perm_btn = ctk.CTkButton(box, text="Ask macOS for permissions", width=200, fg_color="#78350f", command=self._ask_perms)
        self._refresh_perms()

        # live readings
        live = ctk.CTkFrame(box, corner_radius=8)
        live.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(live, text="2. Check it reads the game", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=8, pady=(6, 0))
        self._live_label = ctk.CTkLabel(live, text="Press Detect Roblox first.", justify="left", anchor="w",
                                        wraplength=500, font=ctk.CTkFont(size=12))
        self._live_label.pack(fill="x", padx=8, pady=6)

        # walks
        walks = ctk.CTkFrame(box, corner_radius=8)
        walks.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(walks, text="Walks", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=8, pady=(6, 0))
        self._walks_label = ctk.CTkLabel(walks, text="", justify="left", anchor="w", wraplength=500,
                                         font=ctk.CTkFont(size=12), text_color="#9ca3af")
        self._walks_label.pack(fill="x", padx=8, pady=(0, 6))

        # adjust
        adj = Collapsible(box, "Adjust (only if a reading above looks wrong)")
        adj.pack(fill="x", padx=4, pady=2)
        r = ctk.CTkFrame(adj.body, fg_color="transparent")
        r.pack(fill="x")
        ctk.CTkButton(r, text="Backpack pixel", width=120, command=lambda: self._pick_point(
            "backpack_pixel", "Click 3 px inside the LEFT end of the backpack bar")).pack(side="left", padx=2, pady=2)
        ctk.CTkButton(r, text="Health pixel", width=110, command=lambda: self._pick_point(
            "health_pixel", "Click the middle of the health bar")).pack(side="left", padx=2, pady=2)
        r2 = ctk.CTkFrame(adj.body, fg_color="transparent")
        r2.pack(fill="x")
        ctk.CTkButton(r2, text="Hive prompt", width=120, command=lambda: self._pick_template(
            "hive_prompt", "Stand at your hive, then drag a tight box around the E prompt text")).pack(side="left", padx=2, pady=2)
        ctk.CTkButton(r2, text="Hive view", width=110, command=lambda: self._pick_template(
            "hive_view", "After a reset, drag a small box around part of the hive pad")).pack(side="left", padx=2, pady=2)
        from setup.permission_checker import open_accessibility_settings, open_screen_recording_settings
        r3 = ctk.CTkFrame(adj.body, fg_color="transparent")
        r3.pack(fill="x")
        ctk.CTkButton(r3, text="Screen Recording", width=120, fg_color="#374151", command=open_screen_recording_settings).pack(side="left", padx=2, pady=2)
        ctk.CTkButton(r3, text="Accessibility", width=110, fg_color="#374151", command=open_accessibility_settings).pack(side="left", padx=2, pady=2)

        # record
        rec = Collapsible(box, "Record your own walk (optional, replaces the built in one)")
        rec.pack(fill="x", padx=4, pady=2)
        b = rec.body
        ctk.CTkLabel(b, text="Prepare resets your character. Start, walk to the field with WASD (, . turn, space jump, E cannon), Stop saves it.",
                     wraplength=500, justify="left", font=ctk.CTkFont(size=11), text_color="#9ca3af").pack(anchor="w")
        rr = ctk.CTkFrame(b, fg_color="transparent")
        rr.pack(fill="x", pady=4)
        self._rec_field = ctk.StringVar(value="sunflower")
        ctk.CTkComboBox(rr, values=FIELDS, variable=self._rec_field, width=130).pack(side="left", padx=2)
        ctk.CTkButton(rr, text="Prepare", width=80, fg_color="#78350f", command=self._prepare).pack(side="left", padx=2)
        self._rec_btn = ctk.CTkButton(rr, text="Start", width=70, fg_color="#065f46", command=self._toggle_record)
        self._rec_btn.pack(side="left", padx=2)
        ctk.CTkButton(rr, text="Test", width=60, command=self._test_path).pack(side="left", padx=2)
        ctk.CTkButton(rr, text="Use built in", width=96, fg_color="#374151", command=self._delete_user_path).pack(side="left", padx=2)
        self._msg = ctk.CTkLabel(box, text="", wraplength=520, justify="left", font=ctk.CTkFont(size=11), text_color="#9ca3af")
        self._msg.pack(anchor="w", padx=8, pady=4)

    # ---------------------------------------------------------------- state
    def _refresh_perms(self) -> None:
        from setup import permissions
        problems = permissions.check().problems()
        if problems:
            self._perm_label.configure(text="\n".join(problems), text_color="#f59e0b")
            self._perm_btn.pack(anchor="w", padx=8, pady=2)
        else:
            self._perm_label.configure(text="macOS permissions: all granted", text_color="#22c55e")
            self._perm_btn.pack_forget()

    def _ask_perms(self) -> None:
        from setup import permissions
        permissions.request_all()
        self.after(1500, self._refresh_perms)

    def refresh_status(self) -> None:
        self._dot.configure(text_color="#22c55e" if calibrator.status()["window"] else "#ef4444")
        have = list_fields_with_paths("to_field")
        user = sorted(p.stem for p in (USER_PATHS_DIR / "to_field").glob("*.json")) if (USER_PATHS_DIR / "to_field").exists() else []
        text = f"Natro's default walks are built in for {len(have)} fields and used automatically. Nothing to do here."
        if user:
            text += f"\nYour own walks (these win): {', '.join(user)}."
        self._walks_label.configure(text=text)

    def _need_window(self) -> WindowBounds | None:
        w = calibrator.current_window()
        if w is None:
            self._msg.configure(text="Roblox window not found. Open Roblox in a window and try again.")
        else:
            self._window = w
        return w

    def _detect(self) -> None:
        self._refresh_perms()
        w = self._need_window()
        if w:
            calibrator.seed_defaults(w)
            self._msg.configure(text=f"Found Roblox ({w.width}x{w.height}). Natro's default spots are set.")
            self._start_live()
        self.refresh_status()

    # ---------------------------------------------------------------- adjust
    def _pick_point(self, key: str, text: str) -> None:
        w = self._need_window()
        if not w:
            return

        def picked(x: int, y: int) -> None:
            calibrator.save_point(key, x, y, w)
            self._msg.configure(text=f"{key} saved.")
            self._start_live()

        PointPicker(self.winfo_toplevel(), text, picked)

    def _pick_template(self, key: str, text: str) -> None:
        w = self._need_window()
        if not w:
            return
        cfg = get_config()
        name = cfg.get(f"hud.{key}_template") or f"{key}.png"

        def picked(region: dict) -> None:
            calibrator.save_region(f"{key}_region", region, w)
            ok = calibrator.save_template(name, region)
            cfg.set(f"hud.{key}_template", name)
            cfg.save()
            self._sensors = None
            self._msg.configure(text=f"{key}: {'saved' if ok else 'FAILED to save'}.")
            self._start_live()

        RegionPicker(self.winfo_toplevel(), text, picked)

    # ------------------------------------------------------------------ live
    def _start_live(self) -> None:
        self._sensors = None
        if not self._live:
            self._live = True
            self._tick_live()

    def _tick_live(self) -> None:
        if not self.winfo_exists():
            return
        if not self.winfo_ismapped():          # another tab is showing: do not read the screen
            self.after(1500, self._tick_live)
            return
        try:
            if self._sensors is None:
                from detection.screen_capture import get_screen_capture
                from detection.sensors import ScreenSensors
                self._sensors = ScreenSensors(get_screen_capture(), self._svc._window_bounds, get_config().get_section("hud"))
            s = self._sensors
            raw = s.backpack_raw()
            lines = calibrator.describe_readings(s.roblox_present(), s.last_backpack_rgb, raw, s.backpack_percent(),
                                                 s.health_grey(), s.hive_prompt_visible(), s.hive_view_visible())
            self._live_label.configure(text="\n".join(lines))
        except Exception as exc:
            self._live_label.configure(text=f"error: {exc}")
        self.after(800, self._tick_live)

    # -------------------------------------------------------------- recorder
    def _prepare(self) -> None:
        if self._svc.running:
            self._msg.configure(text="Stop the macro first.")
            return
        self._msg.configure(text="Resetting your character, keep hands off the keyboard...")

        def work():
            try:
                game = self._svc.build_game(threading.Event(), threading.Event())
                ok = game.reset_to_hive()
                game.release_everything()
                msg = "At the hive. Press Start, then walk to the field." if ok else "Could not confirm the hive. You can still record."
            except Exception as exc:
                msg = f"Prepare failed: {exc}"
            self.after(0, lambda: self._msg.configure(text=msg))

        threading.Thread(target=work, daemon=True).start()

    def _toggle_record(self) -> None:
        if self._recorder is None:
            self._recorder = KeyRecorder()
            self._recorder.start()
            self._rec_btn.configure(text="Stop", fg_color="#7f1d1d")
            self._msg.configure(text="Recording... walk now, then press Stop where gathering should start.")
            return
        events = self._recorder.stop()
        self._recorder = None
        self._rec_btn.configure(text="Start", fg_color="#065f46")
        speed = float(get_config().get("game.walk_speed", 28))
        steps = events_to_steps(events, walk_speed=speed)
        if not steps:
            self._msg.configure(text="Nothing recorded.")
            return
        field = self._rec_field.get()
        path = USER_PATHS_DIR / "to_field" / f"{field_slug(field)}.json"
        PathFile(name=field_slug(field), steps=steps, source="recorded in HiveMac", walk_speed=speed).save(path)
        self._msg.configure(text=f"Saved your walk for {field} ({len(steps)} steps). It replaces the built in one.")
        self.refresh_status()

    def _delete_user_path(self) -> None:
        field = self._rec_field.get()
        p = USER_PATHS_DIR / "to_field" / f"{field_slug(field)}.json"
        if p.exists():
            p.unlink()
            self._msg.configure(text=f"Removed your walk for {field}. Using Natro's built in walk again.")
        else:
            self._msg.configure(text=f"No custom walk for {field}; already using Natro's.")
        self.refresh_status()

    def _test_path(self) -> None:
        if self._svc.running:
            self._msg.configure(text="Stop the macro first.")
            return
        field = self._rec_field.get()
        if not find_path_file("to_field", field, get_config().get("game.travel", "walk")):
            self._msg.configure(text=f"No walk for {field}.")
            return
        self._msg.configure(text="Testing: reset, then walk (moves your character). F9 aborts.")

        def work():
            try:
                from macro.game import FieldConfig
                game = self._svc.build_game(threading.Event(), threading.Event())
                ok = game.reset_to_hive() and game.travel_to(FieldConfig.from_dict({"name": field}))
                game.release_everything()
                msg = "Test finished. Are you at the field start?" if ok else "Test did not finish."
            except Exception as exc:
                msg = f"Test failed: {exc}"
            self.after(0, lambda: self._msg.configure(text=msg))

        threading.Thread(target=work, daemon=True).start()
