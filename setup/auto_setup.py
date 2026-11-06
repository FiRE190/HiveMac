"""
Automated project setup: runs on every launch to ensure the environment
is complete. Safe to call multiple times — all operations are idempotent.

Handles:
  - directory creation
  - default config seeding
  - default profile seeding
  - coordinates.json initialization
  - git repository initialization
  - .gitignore creation
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent

DIRS = [
    "config", "state", "profiles", "detection", "ocr",
    "movement", "tasks", "services", "calibration", "ui",
    "utils", "debug", "logs", "templates", "setup",
]

DEFAULT_COORDINATES: dict = {}

DEFAULT_CONFIG_KEYS = {
    "app": {
        "debug_mode": False,
        "emergency_stop_key": "f9",
        "window_width": 480,
        "window_height": 820,
        "theme": "dark",
        "first_run": True,
    },
    "screen": {
        "scale_factor": 2.0,
        "roblox_window": {"left": 0, "top": 0, "width": 0, "height": 0},
        "regions": {
            "backpack_pct": {"left": 0, "top": 0, "width": 0, "height": 0},
        },
    },
    "detection": {
        "backpack_pct_confidence": 0.75,
        "template_match_threshold": 0.80,
        "death_screen_threshold": 0.85,
        "hive_threshold": 0.80,
        "mob_threshold": 0.78,
        "roblox_auto_detect": True,
    },
    "timing": {
        "ui_poll_ms": 200,
        "watchdog_interval_sec": 30,
        "watchdog_timeout_sec": 60,
        "movement_loop_delay_ms": 80,
        "click_hold_ms": 120,
    },
    "movement": {
        "default_pattern": "circular",
        "base_speed": 1.0,
        "randomness": 0.3,
        "micro_pause_chance": 0.08,
        "micro_pause_min_ms": 50,
        "micro_pause_max_ms": 250,
        "use_relative_coords": True,
    },
    "power": {
        "reduce_brightness_on_start": False,
        "brightness_level": 50,
        "caffeinate": True,
    },
    "wealth_clock": {"enabled": True, "interval_min": 61, "reset_character": False},
    "mob_run": {"enabled": True, "interval_min": 64, "max_retries": 3},
    "death_recovery": {"backup_field_farming_min": 30},
    "calibration": {
        "completed": False,
        "roblox_detected": False,
        "hive_set": False,
        "backpack_region_set": False,
        "last_calibration_ts": 0,
    },
}

DEFAULT_PROFILE = {
    "name": "default",
    "target_field": "Sunflower Field",
    "backup_field": "Dandelion Field",
    "movement_pattern": "circular",
    "backpack_threshold_pct": 90,
    "farming_duration_min": 0,
    "mob_run_enabled": True,
    "wealth_clock_enabled": True,
    "sprinkler_enabled": False,
    "randomness": 0.3,
    "wealth_clock_interval_min": 61,
    "mob_run_interval_min": 64,
    "graphics_level": 3,
    "reduce_brightness": False,
    "brightness_level": 50,
    "waypoints": {},
    "mob_route": ["Stump Field", "Mushroom Field", "Spider Field"],
    "hive": {
        "name": "",
        "rel_x": 0.0,
        "rel_y": 0.0,
        "anchor": "roblox_window",
        "detected": False,
    },
    "notes": "",
}

GITIGNORE = """\
__pycache__/
*.pyc
*.pyo
.env
venv/
logs/
debug/
*.log
.DS_Store
config/settings.json
config/last_profile.txt
config/coordinates.json
templates/*.png
"""


def run_full_setup(verbose: bool = True) -> None:
    _log = print if verbose else lambda *a: None

    # ── Directories ─────────────────────────────────────────────────────
    for d in DIRS:
        path = ROOT / d
        path.mkdir(parents=True, exist_ok=True)
    _log("[setup] Directories OK")

    # ── coordinates.json ────────────────────────────────────────────────
    coords_path = ROOT / "config" / "coordinates.json"
    if not coords_path.exists():
        coords_path.write_text(json.dumps(DEFAULT_COORDINATES, indent=2), encoding="utf-8")
        _log("[setup] coordinates.json created")

    # ── settings.json (backfill only, never overwrite user settings) ────
    settings_path = ROOT / "config" / "settings.json"
    if not settings_path.exists():
        settings_path.write_text(json.dumps(DEFAULT_CONFIG_KEYS, indent=2), encoding="utf-8")
        _log("[setup] settings.json created")
    else:
        _backfill_json(settings_path, DEFAULT_CONFIG_KEYS)
        _log("[setup] settings.json backfilled")

    # ── default profile ─────────────────────────────────────────────────
    default_profile_path = ROOT / "profiles" / "default.json"
    if not default_profile_path.exists():
        default_profile_path.write_text(json.dumps(DEFAULT_PROFILE, indent=2), encoding="utf-8")
        _log("[setup] default profile created")

    # ── .gitignore ──────────────────────────────────────────────────────
    gitignore_path = ROOT / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(GITIGNORE, encoding="utf-8")
        _log("[setup] .gitignore created")

    # ── git init ────────────────────────────────────────────────────────
    if not (ROOT / ".git").exists():
        try:
            subprocess.run(
                ["git", "init", str(ROOT)],
                check=True, capture_output=True,
            )
            _log("[setup] Git repository initialized")
        except Exception as e:
            _log(f"[setup] Warning: git init failed: {e}")
    else:
        _log("[setup] Git repository already initialized")

    _log("[setup] Setup complete")


def _backfill_json(path: Path, defaults: dict) -> None:
    """Add any keys present in defaults but missing from the file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    changed = _deep_backfill(data, defaults)
    if changed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


def _deep_backfill(data: dict, defaults: dict) -> bool:
    changed = False
    for k, v in defaults.items():
        if k not in data:
            data[k] = v
            changed = True
        elif isinstance(v, dict) and isinstance(data[k], dict):
            if _deep_backfill(data[k], v):
                changed = True
    return changed


def mark_first_run_complete() -> None:
    settings_path = ROOT / "config" / "settings.json"
    if settings_path.exists():
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("app", {})["first_run"] = False
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


def is_first_run() -> bool:
    settings_path = ROOT / "config" / "settings.json"
    if not settings_path.exists():
        return True
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("app", {}).get("first_run", True)
    except Exception:
        return True
