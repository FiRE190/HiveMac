# BeeSwarm Local Macro

A production-structured, fully local macOS Python macro for Bee Swarm Simulator.  
**Personal use only.**

---

## Features

| Feature | Details |
|---|---|
| Field farming loop | Circular, zig-zag, spiral, corner-rotation, or custom waypoint patterns |
| Backpack detection | OCR reads pollen % — auto-returns to hive at configured threshold |
| Hive task | Navigates to hive, holds convert key until empty, returns to field |
| Wealth Clock | Fires every 61 min (configurable) — interrupts farming, activates clock, resumes |
| Mob Run | Fires every 64 min — full mob route with retry logic |
| Death recovery | Detects respawn — farms backup field 30 min — returns to original |
| Profile system | JSON profiles: create, save, load, delete, auto-loads last used |
| Calibration tool | Record coordinates, test OCR regions, capture templates, test patterns |
| Emergency stop | F9 hotkey (configurable) stops everything immediately |
| Watchdog | Background heartbeat monitor — auto-recovers if macro gets stuck |
| Power management | Optional brightness reduction + caffeinate to prevent sleep |
| Control panel | customtkinter dark UI — Start / Pause / Stop / Debug / Calibrate |

---

## Requirements

- macOS (Apple Silicon or Intel)
- Python 3.9+
- Roblox desktop app (windowed mode preferred)
- Homebrew

---

## Installation

```bash
cd ~/BeeSwarmLocalMacro
bash install.sh
```

This installs Tesseract OCR via Homebrew and all Python packages.

### Manual install

```bash
brew install tesseract
pip3 install -r requirements.txt
```

---

## macOS Permissions (required)

The macro needs two permissions — grant them before running:

1. **Screen Recording**  
   `System Settings → Privacy & Security → Screen Recording`  
   Enable for **Terminal** (or your Python launcher)

2. **Accessibility**  
   `System Settings → Privacy & Security → Accessibility`  
   Enable for **Terminal** (or your Python launcher)

> Without these permissions screen capture and keyboard control will fail silently.

---

## Running

```bash
cd ~/BeeSwarmLocalMacro
python3 main.py
```

The control panel opens, loads your last-used profile, and waits for you to press **START**.

---

## Calibration (do this first)

Before the macro can navigate or detect anything, you must calibrate it.

1. Open Roblox and enter Bee Swarm Simulator (windowed mode)
2. Click **Calibrate** in the control panel
3. **Coordinates tab** — record these key locations by name:
   - `hive` — click on the hive entrance
   - `wealth_clock` — click near the Wealth Clock
   - `sunflower_field` (and any other fields you use)
   - `mob_route_<field>` entries for each mob field
4. **OCR Regions tab** — set the screen region for `backpack_pct`  
   (edit `config/settings.json` → `screen.regions.backpack_pct` with `left/top/width/height`)
5. **Templates tab** — capture screenshots of:
   - `respawn_screen.png` — the death/respawn overlay
   - `hive_ui.png` — the hive conversion prompt
   - `wealth_clock_prompt.png` — the Wealth Clock activate prompt
   - `mob_hp_bar.png` — a mob's HP bar
6. **Test Movement** — verify a pattern runs correctly in-game

---

## Profiles

Profiles are stored as JSON files in `profiles/`.

| Field | Default | Description |
|---|---|---|
| `target_field` | Sunflower Field | Primary farming field |
| `backup_field` | Dandelion Field | Used during death recovery |
| `movement_pattern` | circular | circular / zig-zag / spiral / corner_rotation / waypoint |
| `backpack_threshold_pct` | 90 | % full before returning to hive |
| `wealth_clock_enabled` | true | Enable/disable wealth clock interrupts |
| `mob_run_enabled` | true | Enable/disable mob run interrupts |
| `wealth_clock_interval_min` | 61 | Minutes between wealth clock activations |
| `mob_run_interval_min` | 64 | Minutes between mob runs |
| `randomness` | 0.3 | 0 = robotic, 1 = very random movement |
| `reduce_brightness` | false | Dim display when macro is running |
| `brightness_level` | 50 | Display brightness % when reduced |
| `mob_route` | [Stump, Mushroom, Spider] | Ordered list of mob fields to visit |

---

## Controls

| Button | Action |
|---|---|
| **START** | Begin farming with the active profile |
| **PAUSE** | Suspend movement (press again to resume) |
| **STOP** | Stop all tasks, return to IDLE |
| **Debug** | Enable verbose logging in the console |
| **Calibrate** | Open the calibration tool window |
| **F9** | Emergency stop hotkey (works globally) |

---

## Folder Structure

```
~/BeeSwarmLocalMacro/
├── main.py              Entry point
├── install.sh           Dependency installer
├── requirements.txt
├── config/              Settings JSON, coordinates, OCR regions
├── profiles/            Saved profile JSON files
├── detection/           Screen detection modules
├── ocr/                 Tesseract OCR wrapper
├── movement/            WASD patterns and controller
├── tasks/               Farming, hive, wealth clock, mob run, death recovery
├── services/            FarmingService orchestrator, power manager
├── calibration/         Calibration UI and coordinate recorder
├── ui/                  customtkinter windows and widgets
├── utils/               Logger, watchdog, screenshot logger
├── templates/           OpenCV reference images (captured via calibration)
├── logs/                Rotating log files
└── debug/               Error screenshots
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Screen capture returns black frames | Grant Screen Recording permission in System Settings |
| Keyboard inputs not working | Grant Accessibility permission in System Settings |
| OCR always returns empty | Install tesseract: `brew install tesseract` |
| Template matching never finds anything | Recapture templates via Calibration → Templates tab |
| Macro gets stuck / won't stop | Press **F9** emergency stop; check `logs/macro.log` |
| `customtkinter` import error | `pip3 install customtkinter` |

---

## Required API Keys

None required. The macro is fully offline.

## Optional API Keys

```
CLERK_PUBLISHABLE_KEY  — future cloud profile sync only
CLERK_SECRET_KEY       — future cloud profile sync only
```

Copy `.env.example` → `.env` and fill in if needed.

## Required Local Files (auto-created on first run)

- `config/settings.json` — user config (merged from defaults)
- `config/coordinates.json` — calibrated coordinates
- `profiles/default.json` — default farming profile
- `templates/*.png` — template images (captured via Calibration tool)

---

## Installation Commands (summary)

```bash
# Install
bash install.sh

# Run
python3 main.py

# Emergency manual stop (if UI is unresponsive)
# Press F9 while any window is focused
```
