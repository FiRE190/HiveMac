# HiveMac

A local macOS macro for Bee Swarm Simulator, written in Python. It watches the screen,
reads the HUD with OCR and template matching, and drives the character with keyboard and
mouse input. Nothing touches the game's memory or network.

> **Status: work in progress. It does not run end to end yet.** The calibration tools, the
> farming loop and the navigation stack exist, but they have not been tied together into a
> working session. Expect rough edges and missing pieces.

## Read this first

- Automating gameplay is against Roblox's terms of use. Accounts that use macros can be
  banned. Use at your own risk; nobody here can help with a ban.
- This project is not affiliated with Roblox or the game's developers.
- It was built for personal use and is shared as is, with no support promised.

## What it does (when finished)

| Part | What it does |
|---|---|
| Field farming | Walks a field in circular, zig-zag, spiral, corner or custom waypoint patterns |
| Backpack watch | OCR reads the pollen percentage and returns to the hive at a threshold |
| Hive task | Walks to the hive, converts pollen, walks back |
| Wealth clock | Fires on a timer, interrupts farming, resumes |
| Mob runs | Scheduled detours to clear mobs (early) |
| Death recovery | Detects the respawn screen and restarts the loop |
| Navigation | Route graph between hive and fields with landmark localisation and recovery |
| Watchdog | Emergency stop key (F9 by default) and a stall watchdog |

## Requirements

- macOS on Apple Silicon or Intel, Python 3.10 to 3.12.
- Tesseract for OCR: `brew install tesseract`.
- Two permissions in System Settings > Privacy & Security, granted to your terminal and to
  Python: **Screen Recording** (to see the game) and **Accessibility** (to send input).
- Roblox running in a window, not full screen.

## Install and run

```sh
git clone https://github.com/FiRE190/HiveMac.git
cd HiveMac
./install.sh        # creates a virtual environment and installs requirements.txt
./launch.command    # or: python main.py
```

The first launch opens the setup wizard: it checks permissions, finds the Roblox window,
measures the display scale, lets you pick the HUD regions, and records the hive location.
Settings go to `config/settings.json`, profiles to `profiles/`. Both are yours and are not
committed.

Press **F9** at any time to stop everything.

## What still needs the real game

The code paths are complete and tested as far as they can be without Roblox. These values
can only be settled with the game open, through the calibration tools:

- The backpack % screen region and its colour thresholds (Start refuses to run without the region).
- Cropped templates for the hive UI and the respawn screen, and landmark crops in
  `templates/landmarks/` (the capture tools now save the dragged box, not the whole screen).
- Key durations in `config/nav_map.json`, especially the two wealth clock edges marked
  `_needs_tuning`, and the cannon timing.
- The camera reset key and degrees per rotation tap.

## How the code is organised

```
main.py            entry point: scaffold, logging, dependency check, UI
setup/             first-run setup, environment and permission checks
calibration/       wizard, region picker, coordinate recorder, hive and speed calibration
detection/         screen capture, template matching, HUD detectors (backpack, hive, death, mobs)
ocr/               Tesseract wrapper
perception/        frame manager, template system, fusion of detector results
world_model/       localisation beliefs and navigation health
navigation/        route graph, planner, primitives, validators, recovery, telemetry
planning/          recovery manager
movement/          movement patterns, controllers (walk, cannon, glider), randomiser
execution/         keyboard and mouse input layer
tasks/             farming, hive, wealth clock, mob run, death recovery, scheduler
services/          farming service (runs the task loop), power manager
state/             state machine and shared state
ui/                control panel, log console, profile editor
utils/             logger, watchdog, rolling windows, screenshot logger
templates/         image templates for matching (your own captures, not committed)
```

## Development

```sh
pip install -r requirements-dev.txt
ruff check .   # lint (real errors only while the code is WIP)
pytest         # tests for the pure parts: patterns, randomiser, state machine, rolling windows
```

CI runs the same on every push and pull request. Work happens on `dev`; `main` takes pull
requests once the checks pass.

## License

MIT. See [LICENSE](LICENSE).
