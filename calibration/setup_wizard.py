"""
First-run setup wizard.

A step-by-step window that guides the user through every required
calibration in the correct order. Each step shows clear instructions,
a status badge, and an action button. Progress persists — the wizard
can be closed and reopened without losing completed steps.

Launched automatically from main.py when calibration is incomplete,
and accessible from the main window's Calibrate button at any time.
"""
import threading
import time
from pathlib import Path

import customtkinter as ctk

from calibration.checklist import get_checklist
from calibration.coordinate_recorder import CoordinateRecorder
from calibration.region_picker import RegionPicker
from utils.logger import get_logger

log = get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# ------------------------------------------------------------------ #
# Step definitions (ordered)                                           #
# ------------------------------------------------------------------ #

_STEPS = [
    {
        "title":    "Welcome",
        "category": "info",
        "key":      None,
        "heading":  "Welcome to BeeSwarm Local Macro",
        "body": (
            "This wizard will guide you through the one-time setup.\n\n"
            "You only need to do this once. Everything is saved locally.\n\n"
            "Before continuing:\n"
            "  • Open Roblox and enter Bee Swarm Simulator\n"
            "  • Set Roblox to Windowed mode (Esc → Settings → Display)\n"
            "  • Position Roblox so you can still see this window\n\n"
            "Click Next when ready."
        ),
        "action": None,
    },
    {
        "title":    "Hive coordinate",
        "category": "coordinate",
        "key":      "hive",
        "heading":  "Step 1 — Record your Hive location",
        "body": (
            "Walk your character to your hive entrance in Roblox.\n\n"
            "Then click Record below and immediately click\n"
            "on your hive in the Roblox window.\n\n"
            "This is where the macro will navigate to convert pollen."
        ),
        "action":  "record_coord",
    },
    {
        "title":    "Wealth Clock coordinate",
        "category": "coordinate",
        "key":      "wealth_clock",
        "heading":  "Step 2 — Record the Wealth Clock location",
        "body": (
            "Navigate to the Wealth Clock in Roblox.\n\n"
            "Click Record then click on the Wealth Clock\n"
            "in the Roblox window.\n\n"
            "The macro visits this every 61 minutes (configurable)."
        ),
        "action":  "record_coord",
    },
    {
        "title":    "Farming field coordinate",
        "category": "coordinate",
        "key":      "sunflower_field",
        "heading":  "Step 3 — Record your primary farming field",
        "body": (
            "Walk to the center of the field you plan to farm most.\n\n"
            "Click Record then click on the field in Roblox.\n\n"
            "This saves it as 'sunflower_field'. To record other fields,\n"
            "use the full Calibration tool after this wizard."
        ),
        "action":  "record_coord",
    },
    {
        "title":    "Hive UI template",
        "category": "template",
        "key":      "hive_ui.png",
        "heading":  "Step 4 — Capture the Hive conversion prompt",
        "body": (
            "In Roblox, walk up to your hive until you see\n"
            "the 'Convert Pollen' or 'E to collect' prompt.\n\n"
            "Keep that prompt visible, then click Capture below.\n"
            "You have 3 seconds to switch to Roblox after clicking."
        ),
        "action":  "capture_template",
    },
    {
        "title":    "Death screen template",
        "category": "template",
        "key":      "respawn_screen.png",
        "heading":  "Step 5 — Capture the death / respawn screen",
        "body": (
            "Deliberately die in Roblox (jump off a high ledge).\n\n"
            "When the respawn/death overlay appears on screen,\n"
            "click Capture. You have 3 seconds to switch to Roblox.\n\n"
            "The macro uses this to detect when you've died."
        ),
        "action":  "capture_template",
    },
    {
        "title":    "Wealth Clock template",
        "category": "template",
        "key":      "wealth_clock_prompt.png",
        "heading":  "Step 6 — Capture the Wealth Clock prompt",
        "body": (
            "Stand next to the Wealth Clock in Roblox until\n"
            "the activation prompt appears on screen.\n\n"
            "Keep that prompt visible, then click Capture.\n"
            "You have 3 seconds to switch to Roblox after clicking."
        ),
        "action":  "capture_template",
    },
    {
        "title":    "Backpack % region",
        "category": "ocr",
        "key":      "backpack_pct",
        "heading":  "Step 7 — Select the backpack percentage area",
        "body": (
            "Your pollen percentage is shown somewhere on the Roblox HUD\n"
            "(usually top-right area).\n\n"
            "Click 'Select Region' — a dark overlay will appear.\n"
            "Drag a rectangle around just the percentage number.\n\n"
            "After selecting, you'll see a preview with the OCR result."
        ),
        "action":  "pick_region",
    },
    {
        "title":    "Done",
        "category": "info",
        "key":      None,
        "heading":  "Setup complete!",
        "body": (
            "All required calibrations are saved.\n\n"
            "You can now press START in the control panel.\n\n"
            "Tips:\n"
            "  • Use the Calibration tool to add more field coordinates\n"
            "  • Capture a mob HP bar template for Mob Run detection\n"
            "  • Press F9 at any time as an emergency stop\n\n"
            "Good luck farming!"
        ),
        "action":  None,
    },
]


class SetupWizard(ctk.CTkToplevel):
    def __init__(self, parent, start_step: int = 0) -> None:
        super().__init__(parent)
        self.title("First-Time Setup Wizard")
        self.geometry("540x480")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self._step_index  = start_step
        self._recorder    = CoordinateRecorder()
        self._build_ui()
        self._render_step()

    # ------------------------------------------------------------------ #
    # UI skeleton                                                          #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        # Progress bar + step counter
        top = ctk.CTkFrame(self, height=44, corner_radius=0, fg_color="#111827")
        top.pack(fill="x")
        top.pack_propagate(False)

        self._progress_label = ctk.CTkLabel(
            top, text="", font=ctk.CTkFont(size=11), text_color="#9ca3af"
        )
        self._progress_label.pack(side="right", padx=14, pady=12)

        self._progress_bar = ctk.CTkProgressBar(top, width=280, height=8)
        self._progress_bar.pack(side="left", padx=14, pady=18)
        self._progress_bar.set(0)

        # Main content area
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(fill="both", expand=True, padx=24, pady=16)

        # Navigation buttons
        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="x", padx=24, pady=(0, 16))

        self._back_btn = ctk.CTkButton(
            nav, text="← Back", width=90, command=self._prev_step,
            fg_color="#374151", hover_color="#4b5563",
        )
        self._back_btn.pack(side="left")

        self._next_btn = ctk.CTkButton(
            nav, text="Next →", width=90, command=self._next_step,
        )
        self._next_btn.pack(side="right")

        self._skip_btn = ctk.CTkButton(
            nav, text="Skip", width=70, command=self._skip_step,
            fg_color="transparent", hover_color="#374151", text_color="#6b7280",
        )
        self._skip_btn.pack(side="right", padx=8)

    # ------------------------------------------------------------------ #
    # Step rendering                                                       #
    # ------------------------------------------------------------------ #

    def _render_step(self) -> None:
        for w in self._content.winfo_children():
            w.destroy()

        step  = _STEPS[self._step_index]
        total = len(_STEPS)

        # Progress
        progress = self._step_index / (total - 1) if total > 1 else 1.0
        self._progress_bar.set(progress)
        self._progress_label.configure(
            text=f"Step {self._step_index + 1} of {total}"
        )

        # Back button disabled on first step
        self._back_btn.configure(state="normal" if self._step_index > 0 else "disabled")

        # Last step: rename Next to Finish
        if self._step_index == total - 1:
            self._next_btn.configure(text="Finish")
            self._skip_btn.configure(state="disabled")
        else:
            self._next_btn.configure(text="Next →")
            self._skip_btn.configure(state="normal")

        # Heading
        heading_color = {
            "coordinate": "#3b82f6",
            "template":   "#f59e0b",
            "ocr":        "#22c55e",
            "info":       "#9ca3af",
        }.get(step["category"], "#9ca3af")

        ctk.CTkLabel(
            self._content,
            text=step["heading"],
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=heading_color,
            anchor="w",
        ).pack(fill="x", pady=(0, 12))

        # Category badge
        badge_text = {
            "coordinate": "COORDINATE",
            "template":   "TEMPLATE",
            "ocr":        "OCR REGION",
            "info":       "",
        }.get(step["category"], "")
        if badge_text:
            ctk.CTkLabel(
                self._content,
                text=f"  {badge_text}  ",
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color=heading_color,
                corner_radius=4,
                text_color="white",
                width=10,
            ).pack(anchor="w", pady=(0, 10))

        # Body text
        ctk.CTkLabel(
            self._content,
            text=step["body"],
            wraplength=470,
            justify="left",
            anchor="w",
            font=ctk.CTkFont(size=13),
            text_color="#d1d5db",
        ).pack(fill="x", pady=(0, 16))

        # Status badge (shows if this item is already done)
        if step["key"]:
            self._status_label = ctk.CTkLabel(
                self._content, text="", font=ctk.CTkFont(size=12)
            )
            self._status_label.pack(anchor="w", pady=(0, 8))
            self._refresh_status(step)

        # Action button
        action = step.get("action")
        if action == "record_coord":
            self._action_btn = ctk.CTkButton(
                self._content,
                text="Record (click on Roblox after pressing)",
                command=self._do_record_coord,
                fg_color="#1d4ed8",
                hover_color="#1e40af",
                height=36,
            )
            self._action_btn.pack(anchor="w")

        elif action == "capture_template":
            self._action_btn = ctk.CTkButton(
                self._content,
                text="Capture (3s delay — switch to Roblox)",
                command=self._do_capture_template,
                fg_color="#92400e",
                hover_color="#78350f",
                height=36,
            )
            self._action_btn.pack(anchor="w")

        elif action == "pick_region":
            self._action_btn = ctk.CTkButton(
                self._content,
                text="Select Region (drag over Roblox HUD)",
                command=self._do_pick_region,
                fg_color="#14532d",
                hover_color="#15803d",
                height=36,
            )
            self._action_btn.pack(anchor="w")

    def _refresh_status(self, step: dict) -> None:
        checklist = {item.key: item for item in get_checklist()}
        item = checklist.get(step["key"])
        if item:
            if item.ok:
                self._status_label.configure(
                    text=f"✓  Already done — {item.detail}",
                    text_color="#22c55e",
                )
            else:
                self._status_label.configure(
                    text=f"✗  {item.detail}",
                    text_color="#ef4444",
                )

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def _do_record_coord(self) -> None:
        step = _STEPS[self._step_index]
        key  = step["key"]
        self._action_btn.configure(text=f"Waiting for click to save '{key}'...", state="disabled")

        def _on_saved(name, x, y):
            self.after(0, lambda: self._action_btn.configure(
                text=f"✓ Saved '{name}' = ({x}, {y})",
                state="normal",
                fg_color="#14532d",
            ))
            self.after(0, lambda: self._refresh_status(step))

        self._recorder.start_recording(key, on_saved=_on_saved)

    def _do_capture_template(self) -> None:
        step     = _STEPS[self._step_index]
        filename = step["key"]
        self._action_btn.configure(text="Drag a box around it in Roblox...", state="disabled")
        from calibration.region_picker import RegionPicker
        from calibration.calibration_tool import crop_to_region
        from detection.screen_capture import get_screen_capture

        def _run(region: dict):
            time.sleep(1)
            try:
                import cv2
                _TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
                img = crop_to_region(get_screen_capture().capture_full(), region)
                path = _TEMPLATES_DIR / filename
                cv2.imwrite(str(path), img)
                log.info("Template saved: %s", path)
                self.after(0, lambda: self._action_btn.configure(
                    text=f"✓ Captured {filename}",
                    state="normal",
                    fg_color="#14532d",
                ))
                self.after(0, lambda: self._refresh_status(step))
            except Exception as e:
                log.error("Template capture failed: %s", e)
                self.after(0, lambda: self._action_btn.configure(
                    text="Capture failed — try again",
                    state="normal",
                ))

        def _picked(_key: str, region: dict) -> None:
            threading.Thread(target=_run, args=(region,), daemon=True).start()

        self.after(200, lambda: RegionPicker(self, f"template:{filename}", on_saved=_picked).show())

    def _do_pick_region(self) -> None:
        step = _STEPS[self._step_index]
        key  = step["key"]

        def _on_region_saved(name, region):
            self.after(0, lambda: self._action_btn.configure(
                text=f"✓ Region saved ({region['width']}×{region['height']}px)",
                state="normal",
                fg_color="#14532d",
            ))
            self.after(0, lambda: self._refresh_status(step))

        self._action_btn.configure(state="disabled", text="Opening overlay...")
        # Small delay so button updates before overlay appears
        self.after(200, lambda: RegionPicker(self, key, on_saved=_on_region_saved).show())
        self.after(300, lambda: self._action_btn.configure(state="normal", text="Select Region (drag over Roblox HUD)"))

    # ------------------------------------------------------------------ #
    # Navigation                                                           #
    # ------------------------------------------------------------------ #

    def _next_step(self) -> None:
        if self._step_index >= len(_STEPS) - 1:
            self._recorder.stop()
            self.destroy()
            return
        self._step_index += 1
        self._render_step()

    def _prev_step(self) -> None:
        if self._step_index > 0:
            self._step_index -= 1
            self._render_step()

    def _skip_step(self) -> None:
        self._next_step()

    def destroy(self) -> None:
        self._recorder.stop()
        super().destroy()


def should_show_wizard() -> bool:
    """Returns True if any required calibration item is incomplete."""
    from calibration.checklist import all_required_complete
    return not all_required_complete()
