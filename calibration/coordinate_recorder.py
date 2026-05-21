"""
Records named screen coordinates using a pynput mouse listener.
Saves to config/coordinates.json.

Usage:
  recorder = CoordinateRecorder()
  recorder.start_recording("hive")   # next click will save as "hive"
  recorder.stop()
"""
import json
import threading
from pathlib import Path
from typing import Callable, Optional

from pynput import mouse

from detection.screen_capture import get_screen_capture
from utils.logger import get_logger

log = get_logger(__name__)

_COORDS_FILE = Path(__file__).parent.parent / "config" / "coordinates.json"


def _load_coords() -> dict:
    if _COORDS_FILE.exists():
        with open(_COORDS_FILE, "r") as f:
            return json.load(f)
    return {}


def _save_coords(data: dict) -> None:
    _COORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_COORDS_FILE, "w") as f:
        json.dump(data, f, indent=2)


class CoordinateRecorder:
    def __init__(self) -> None:
        self._listener: Optional[mouse.Listener] = None
        self._pending_name: Optional[str] = None
        self._on_saved: Optional[Callable[[str, int, int], None]] = None
        self._lock = threading.Lock()

    def start_recording(self, name: str, on_saved: Optional[Callable] = None) -> None:
        """
        Arm the recorder. The next left-click will be saved as `name`.
        on_saved(name, x, y) is called when the coordinate is captured.
        """
        with self._lock:
            self._pending_name = name
            self._on_saved = on_saved

        if self._listener is None:
            self._listener = mouse.Listener(on_click=self._on_click)
            self._listener.daemon = True
            self._listener.start()
            log.info("CoordinateRecorder: listening for click (name='%s')", name)
        else:
            log.info("CoordinateRecorder: will record next click as '%s'", name)

    def _on_click(self, x: int, y: int, button, pressed: bool) -> None:
        if not pressed or button != mouse.Button.left:
            return
        with self._lock:
            name = self._pending_name
            if name is None:
                return
            self._pending_name = None
            callback = self._on_saved

        coords = _load_coords()
        coords[name] = {"x": x, "y": y}
        _save_coords(coords)
        log.info("Saved coordinate '%s' = (%d, %d)", name, x, y)

        if callback:
            try:
                callback(name, x, y)
            except Exception as e:
                log.error("on_saved callback error: %s", e)

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None

    def list_coordinates(self) -> dict:
        return _load_coords()

    def delete_coordinate(self, name: str) -> bool:
        coords = _load_coords()
        if name in coords:
            del coords[name]
            _save_coords(coords)
            log.info("Deleted coordinate '%s'", name)
            return True
        return False
