# HiveMac, the Python version (older)

The native Swift app in `swift/` is the main HiveMac now. This page keeps the notes for the
older Python app that still lives in this repository.

A macOS macro for Bee Swarm Simulator (Roblox), written in Python. It works the way
Natro Macro does on Windows: reset the character to get back to the hive, convert,
replay a recorded hive to field walk, gather in a pattern until the backpack pixel
says full, reset again. Pixel colour checks at a few fixed spots, no OCR, no OpenCV,
no full screen captures in the loop.

> **Status: built and unit tested, not yet run against the game.** The loop runs
> end to end against a simulated game in the tests. The first live session is the
> next step; see `docs/LIVE_TEST_CHECKLIST.md`.

## Read this first

- Automating gameplay is against Roblox's terms of use. Accounts that use macros can be
  banned. Use at your own risk.
- This project is not affiliated with Roblox or the game's developers.
- Personal use, shared as is.

## How it works

1. **Reset to hive.** Esc, R, Enter. The health bar pixel goes grey and comes back;
   that is the respawn. The hive E prompt template confirms you are at your hive, the
   camera is rotated until the hive view template is seen, turned 180 degrees and zoomed
   fully out. Death lands on exactly the same path.
2. **Convert.** Press E, wait until the backpack pixel reads empty.
3. **Travel.** Replay `config/paths/.../to_field/<field>.json`: key holds in tiles that
   scale with your walk speed, camera taps, a cannon variant where Natro has one. Then
   walk to the start corner and drop the sprinkler.
4. **Gather.** One of Natro's twelve patterns (corner x snake, e_lol, squares, ...)
   with the mouse button held. Between steps: death check, backpack check, time limit,
   lost screen check.
5. Repeat with the next enabled field.

Everything the macro sees is one pixel or one small region relative to the Roblox
window. A small grab costs about 0.15 ms of CPU.

## Requirements

- macOS, Python 3.10 to 3.13 with Tk (`brew install python@3.12 python-tk@3.12`).
- Screen Recording and Accessibility permission for your terminal.
- Roblox in a window (not full screen), camera mode Classic, movement mode Keyboard,
  graphics set manually to a low level, performance stats and micro profiler off,
  camera not inverted, English, background transparency 0. Display colour profile
  sRGB (the backpack colour ladder expects it).
- Your in game walk speed (settings panel) and hive slot (1 to 6 from the ramp).

## Install and run

As an app (recommended, so macOS lists the permissions under "HiveMac"):

```sh
brew install python@3.12 python-tk@3.12
git clone https://github.com/FiRE190/HiveMac.git
cd HiveMac
scripts/install.sh      # builds HiveMac.app and copies it to /Applications
```

Then open HiveMac from Launchpad. On the first run, allow it under System Settings >
Privacy & Security for Screen Recording, Accessibility and Input Monitoring, and open it
again. A zip of the app is attached to each GitHub Release; it needs the same Homebrew
Python at the same path, so the command above is the reliable route.

From the source folder instead (permissions then belong to your terminal):

```sh
./install.sh
./launch.command        # or: venv/bin/python main.py
```

Then the **Calibrate** tab: press **Detect Roblox** (it fills in Natro's default spots)
and check the live readings. Natro's default walks for every field are built in; recording
your own is optional. **Settings**: walk speed, hive slot, sprinkler
type and hotbar key, default travel (walk or cannon). **Fields**: the fields to farm
with pattern, size, width, minutes, backpack percent and so on; blank means Natro's
default for that field.

**F9** stops everything.

### Remote control

The window shows a link like `http://192.168.x.x:8765/?t=...`. Open it on your phone
(same Wi-Fi or Tailscale) to start, pause, stop, change settings and fields, and see
the log. The token in the link is the only protection, so do not expose the port to
the internet.

## Uninstall

Quit HiveMac, delete `HiveMac.app` from Applications, and delete the data folder
`~/Library/Application Support/HiveMac` (settings, profiles, logs, recordings). Then remove
HiveMac from Screen Recording, Accessibility and Input Monitoring in System Settings.

## Layout

```
main.py                 entry point
macro/game.py           reset, convert, travel, gather, walk back (against Sensors and Actuator protocols)
macro/loop.py           the field rotation loop
movement/walk.py        hold keys for tiles at the walk speed, stop and pause aware
movement/paths.py       path step format, loader, Natro .ahk converter
movement/patterns.py    Natro's gather patterns and per field defaults
movement/sprinkler.py   start corner and sprinkler placement
detection/hud.py        backpack colour ladder, grey check, numpy template search (pure)
detection/sensors.py    the real sensors: layout + screen capture
detection/screen_capture.py   mss region grabs
execution/input_interface.py  pynput keys and mouse, the only input module
calibration/            window finder, relative layout, pickers, calibrator, key recorder
services/farming_service.py   owns the loop thread, state, remote controller
remote/server.py        token protected HTTP page and JSON API
ui/                     control panel: Fields, Settings, Calibrate, Log tabs
config/paths/natro/     paths converted from Natro Macro (GPL-3.0 data, see its README)
config/paths/user/      your own recordings (take priority)
tools/convert_natro_paths.py  the converter
docs/RESEARCH.md        how Natro and the other macros work, with file references
```

## Development

```sh
venv/bin/ruff check .
venv/bin/python -m compileall -q . -x venv
venv/bin/python -m pytest -q      # 40 tests, no screen access
```

Work happens on `dev`; `main` takes pull requests once the checks pass.

## License

MIT, except `config/paths/natro/` which is data derived from Natro Macro (GPL-3.0).
