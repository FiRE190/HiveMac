"""
Calibration tool window: tabbed UI for recording coordinates, verifying OCR
regions, capturing templates, and testing movement patterns.

Opened from the main window's Calibration button.
"""
import threading
import time
from pathlib import Path

import customtkinter as ctk

from calibration.coordinate_recorder import CoordinateRecorder
from detection.screen_capture import get_screen_capture
from ocr.ocr_manager import get_ocr
from movement.movement_controller import get_movement_controller
from movement.patterns import PatternFactory
from utils.logger import get_logger

log = get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def crop_to_region(img, region: dict):
    """Crop a full-screen capture (physical pixels) to a region given in screen points."""
    from config.config_manager import get_config
    scale = float(get_config().get("screen.scale_factor", 1.0) or 1.0)
    left = int(region["left"] * scale)
    top = int(region["top"] * scale)
    right = left + int(region["width"] * scale)
    bottom = top + int(region["height"] * scale)
    h, w = img.shape[:2]
    return img[max(0, top):min(h, bottom), max(0, left):min(w, right)]
_COORDS_FILE = Path(__file__).parent.parent / "config" / "coordinates.json"


class CalibrationWindow(ctk.CTkToplevel):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.title("Calibration Tool")
        self.geometry("640x520")
        self.resizable(False, False)

        self._recorder = CoordinateRecorder()
        self._build_ui()

    def _build_ui(self) -> None:
        self._tabs = ctk.CTkTabview(self, width=620, height=480)
        self._tabs.pack(padx=10, pady=10, fill="both", expand=True)

        self._tabs.add("Coordinates")
        self._tabs.add("OCR Regions")
        self._tabs.add("Templates")
        self._tabs.add("Test Movement")

        self._build_coords_tab()
        self._build_ocr_tab()
        self._build_templates_tab()
        self._build_movement_tab()

    # ------------------------------------------------------------------ #
    # Coordinates Tab                                                      #
    # ------------------------------------------------------------------ #

    def _build_coords_tab(self) -> None:
        tab = self._tabs.tab("Coordinates")

        ctk.CTkLabel(tab, text="Coordinate name:").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self._coord_name_entry = ctk.CTkEntry(tab, width=180, placeholder_text="e.g. hive")
        self._coord_name_entry.grid(row=0, column=1, padx=8, pady=8)

        self._record_btn = ctk.CTkButton(
            tab, text="Record (next click)", command=self._start_recording, width=160
        )
        self._record_btn.grid(row=0, column=2, padx=8, pady=8)

        self._coord_status = ctk.CTkLabel(tab, text="", text_color="gray")
        self._coord_status.grid(row=1, column=0, columnspan=3, sticky="w", padx=8)

        # Coordinate list
        ctk.CTkLabel(tab, text="Saved coordinates:").grid(row=2, column=0, sticky="w", padx=8, pady=(10, 2))
        self._coords_text = ctk.CTkTextbox(tab, width=580, height=200, state="disabled")
        self._coords_text.grid(row=3, column=0, columnspan=3, padx=8, pady=4)

        ctk.CTkButton(tab, text="Refresh", command=self._refresh_coords, width=100).grid(
            row=4, column=0, padx=8, pady=8, sticky="w"
        )
        ctk.CTkButton(tab, text="Delete selected", command=self._delete_coord, width=130).grid(
            row=4, column=1, padx=8, pady=8
        )

        self._refresh_coords()

    def _start_recording(self) -> None:
        name = self._coord_name_entry.get().strip()
        if not name:
            self._coord_status.configure(text="Enter a coordinate name first", text_color="red")
            return
        self._coord_status.configure(text=f"Click anywhere in Roblox to save '{name}'...", text_color="yellow")
        self._recorder.start_recording(name, on_saved=self._on_coord_saved)

    def _on_coord_saved(self, name: str, x: int, y: int) -> None:
        self.after(0, lambda: self._coord_status.configure(
            text=f"Saved: '{name}' = ({x}, {y})", text_color="green"
        ))
        self.after(0, self._refresh_coords)

    def _refresh_coords(self) -> None:
        coords = self._recorder.list_coordinates()
        self._coords_text.configure(state="normal")
        self._coords_text.delete("1.0", "end")
        for name, val in sorted(coords.items()):
            self._coords_text.insert("end", f"  {name:30s}  ({val['x']}, {val['y']})\n")
        self._coords_text.configure(state="disabled")

    def _delete_coord(self) -> None:
        name = self._coord_name_entry.get().strip()
        if self._recorder.delete_coordinate(name):
            self._coord_status.configure(text=f"Deleted '{name}'", text_color="orange")
            self._refresh_coords()

    # ------------------------------------------------------------------ #
    # OCR Regions Tab                                                      #
    # ------------------------------------------------------------------ #

    def _build_ocr_tab(self) -> None:
        tab = self._tabs.tab("OCR Regions")

        ctk.CTkLabel(tab, text="Region name:").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self._ocr_region_entry = ctk.CTkEntry(tab, width=180, placeholder_text="e.g. backpack_pct")
        self._ocr_region_entry.grid(row=0, column=1, padx=8)

        ctk.CTkButton(tab, text="Test OCR", command=self._test_ocr, width=120).grid(
            row=0, column=2, padx=8
        )
        ctk.CTkButton(tab, text="Set Region (drag)", command=self._set_region, width=140).grid(
            row=1, column=0, padx=8, pady=4
        )

        self._ocr_result = ctk.CTkTextbox(tab, width=580, height=180, state="disabled")
        self._ocr_result.grid(row=2, column=0, columnspan=3, padx=8, pady=8)

    def _test_ocr(self) -> None:
        name = self._ocr_region_entry.get().strip()
        if not name:
            return
        ocr = get_ocr()
        text = ocr.read_region(name)
        num = ocr.read_number(name)
        self._ocr_result.configure(state="normal")
        self._ocr_result.delete("1.0", "end")
        self._ocr_result.insert("end", f"Region: {name}\nRaw text: '{text}'\nParsed number: {num}\n")
        self._ocr_result.configure(state="disabled")

    def _set_region(self) -> None:
        name = self._ocr_region_entry.get().strip()
        if not name:
            return
        self._ocr_result.configure(state="normal")
        self._ocr_result.delete("1.0", "end")
        self._ocr_result.insert("end", f"Region setting for '{name}' — use the main Calibration config\nto set left/top/width/height in settings.json > screen.regions.{name}\n")
        self._ocr_result.configure(state="disabled")

    # ------------------------------------------------------------------ #
    # Templates Tab                                                        #
    # ------------------------------------------------------------------ #

    def _build_templates_tab(self) -> None:
        tab = self._tabs.tab("Templates")

        ctk.CTkLabel(tab, text="Template name:").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self._tpl_name_entry = ctk.CTkEntry(tab, width=220, placeholder_text="e.g. hive_ui.png")
        self._tpl_name_entry.grid(row=0, column=1, padx=8)

        ctk.CTkButton(tab, text="Capture region (3s)", command=self._capture_template, width=160).grid(
            row=0, column=2, padx=8
        )

        self._tpl_status = ctk.CTkLabel(tab, text="", text_color="gray")
        self._tpl_status.grid(row=1, column=0, columnspan=3, sticky="w", padx=8)

        # List existing templates
        ctk.CTkLabel(tab, text="Saved templates:").grid(row=2, column=0, sticky="w", padx=8, pady=(10, 2))
        self._tpl_text = ctk.CTkTextbox(tab, width=580, height=180, state="disabled")
        self._tpl_text.grid(row=3, column=0, columnspan=3, padx=8, pady=4)
        self._refresh_templates()

    def _capture_template(self) -> None:
        name = self._tpl_name_entry.get().strip()
        if not name:
            self._tpl_status.configure(text="Enter a template filename", text_color="red")
            return

        self._tpl_status.configure(text="Drag a box around the thing to match (switch to Roblox first)",
                                   text_color="yellow")
        from calibration.region_picker import RegionPicker

        def _picked(_key: str, region: dict) -> None:
            threading.Thread(target=self._do_capture, args=(name, region), daemon=True).start()

        self.after(200, lambda: RegionPicker(self, f"template:{name}", on_saved=_picked).show())

    def _do_capture(self, name: str, region: dict) -> None:
        """Save only the dragged region as the template. A whole-screen capture can never
        match anything, so templates must be crops. Landmark names go to templates/landmarks/."""
        time.sleep(1)
        sc = get_screen_capture()
        img_array = crop_to_region(sc.capture_full(), region)
        stem = name[:-4] if name.endswith(".png") else name
        from navigation.node_names import landmark_to_node
        target_dir = _TEMPLATES_DIR / "landmarks" if landmark_to_node(stem) else _TEMPLATES_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / (stem + ".png")

        import cv2
        cv2.imwrite(str(path), img_array)
        log.info("Template saved: %s", path)
        self.after(0, lambda: self._tpl_status.configure(
            text=f"Saved: {path.name}", text_color="green"
        ))
        self.after(0, self._refresh_templates)

    def _refresh_templates(self) -> None:
        _TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        self._tpl_text.configure(state="normal")
        self._tpl_text.delete("1.0", "end")
        for p in sorted(_TEMPLATES_DIR.glob("*.png")):
            self._tpl_text.insert("end", f"  {p.name}\n")
        self._tpl_text.configure(state="disabled")

    # ------------------------------------------------------------------ #
    # Test Movement Tab                                                    #
    # ------------------------------------------------------------------ #

    def _build_movement_tab(self) -> None:
        tab = self._tabs.tab("Test Movement")

        ctk.CTkLabel(tab, text="Pattern:").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self._pattern_var = ctk.StringVar(value="circular")
        self._pattern_menu = ctk.CTkOptionMenu(
            tab, values=["circular", "zig-zag", "spiral", "corner_rotation"],
            variable=self._pattern_var, width=150
        )
        self._pattern_menu.grid(row=0, column=1, padx=8)

        ctk.CTkLabel(tab, text="Duration (sec):").grid(row=1, column=0, padx=8, pady=4, sticky="w")
        self._duration_entry = ctk.CTkEntry(tab, width=80, placeholder_text="5")
        self._duration_entry.insert(0, "5")
        self._duration_entry.grid(row=1, column=1, padx=8, sticky="w")

        ctk.CTkButton(tab, text="Run pattern (switch to Roblox in 3s)", command=self._run_test_movement, width=280).grid(
            row=2, column=0, columnspan=2, padx=8, pady=12
        )

        self._move_status = ctk.CTkLabel(tab, text="", text_color="gray")
        self._move_status.grid(row=3, column=0, columnspan=2, sticky="w", padx=8)

    def _run_test_movement(self) -> None:
        try:
            duration = float(self._duration_entry.get().strip() or "5")
        except ValueError:
            duration = 5.0
        pattern_name = self._pattern_var.get()
        self._move_status.configure(text=f"Running '{pattern_name}' for {duration}s in 3s...", text_color="yellow")
        threading.Thread(target=self._do_movement_test, args=(pattern_name, duration), daemon=True).start()

    def _do_movement_test(self, pattern_name: str, duration: float) -> None:
        time.sleep(3)
        mc = get_movement_controller()
        pattern = PatternFactory.create(pattern_name, radius=60, speed=1.0, randomness=0.3)
        stop = threading.Event()
        mc.move_pattern(pattern, duration, stop_event=stop)
        self.after(0, lambda: self._move_status.configure(
            text=f"Done running '{pattern_name}'", text_color="green"
        ))

    def destroy(self) -> None:
        self._recorder.stop()
        super().destroy()
