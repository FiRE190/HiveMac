"""
Dry run cost measurement. Runs the real gather loop and the real pixel sensors
against whatever is on screen, but with a keyboard and mouse that do nothing, so
no input is ever sent. Prints CPU use of this process and its memory.

  venv/bin/python tools/measure_cpu.py [gather_seconds] [wait_seconds]

The sensors read the screen at their normal rate (backpack, health, death) and
the walker sleeps in 50 ms slices, exactly as in a real session. WindowServer
time for the captures shows up under WindowServer in Activity Monitor, not here.
"""
from __future__ import annotations

import os
import resource
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from calibration.layout import WindowBounds, natro_defaults  # noqa: E402
from detection.screen_capture import get_screen_capture  # noqa: E402
from detection.sensors import ScreenSensors  # noqa: E402
from macro.game import FieldConfig, Game, GameSettings  # noqa: E402
from movement.walk import RealClock  # noqa: E402


class NullActuator:
    def key_down(self, k): ...
    def key_up(self, k): ...
    def tap(self, k, hold_s=0.03): ...
    def mouse_down(self): ...
    def mouse_up(self): ...
    def move_mouse(self, x, y): ...
    def release_all(self): ...


def rss_mb() -> float:
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True).stdout.strip()
    return int(out) / 1024.0 if out else 0.0


def footprint_mb() -> float | None:
    try:
        out = subprocess.run(["footprint", str(os.getpid())], capture_output=True, text=True, timeout=10).stdout
        for line in out.splitlines():
            if "Footprint" in line and "Physical" not in line:
                parts = line.split()
                for i, tok in enumerate(parts):
                    if tok in ("MB", "KB", "GB") and i:
                        v = float(parts[i - 1])
                        return v * {"KB": 1 / 1024, "MB": 1, "GB": 1024}[tok]
    except Exception:
        pass
    return None


def measure(label: str, fn) -> None:
    c0, w0 = time.process_time(), time.perf_counter()
    fn()
    cpu, wall = time.process_time() - c0, time.perf_counter() - w0
    print(f"{label:28s} cpu {cpu:6.2f}s over {wall:5.1f}s wall  =  {100 * cpu / wall:5.2f}% of one core")


def main() -> None:
    gather_s = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    wait_s = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    cap = get_screen_capture()
    import mss
    with mss.mss() as sct:
        m = sct.monitors[1]
    win = WindowBounds(0, 0, min(1280, m["width"]), min(720, m["height"]))
    hud = {k: v for k, v in natro_defaults(win).items()}
    hud.update({"hive_prompt_template": "", "hive_view_template": ""})
    sensors = ScreenSensors(cap, lambda: win, hud)
    game = Game(NullActuator(), sensors, GameSettings(), RealClock(), stop_event=threading.Event(),
                window_size=lambda: (win.left, win.top, win.width, win.height))
    print(f"start: rss {rss_mb():.0f} MB")
    field = FieldConfig.from_dict({"name": "sunflower", "minutes": gather_s / 60.0, "backpack_percent": 101})
    measure(f"gather ({gather_s:.0f}s)", lambda: game.gather(field))
    measure(f"waiting ({wait_s:.0f}s)", lambda: game.walker.wait(wait_s))
    fp = footprint_mb()
    print(f"end:   rss {rss_mb():.0f} MB, peak rss {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1048576:.0f} MB"
          + (f", footprint {fp:.0f} MB" if fp else ""))


if __name__ == "__main__":
    main()
