# HiveMac

[![check](https://github.com/jonathanbrantner/HiveMac/actions/workflows/check.yml/badge.svg)](https://github.com/jonathanbrantner/HiveMac/actions/workflows/check.yml)
![status: beta](https://img.shields.io/badge/status-beta-f2b134)
![macOS 14+](https://img.shields.io/badge/macOS-14%2B-lightgrey)
![Swift](https://img.shields.io/badge/Swift-native-orange)

**A small native macOS app that farms Bee Swarm Simulator for you.** Pick the fields, how long to
stay on each, and press Start. About 30 MB of memory, no Python, no extra installs.

<p align="center">
  <img src="docs/images/shot-fields.png" width="360" alt="Fields tab: your run, one row per field">
  <img src="docs/images/shot-macro.png" width="360" alt="Macro tab: hive, walking, sprinkler and hotbar">
</p>

> **Beta.** HiveMac builds, passes its 70+ tests and runs against a simulated game. It has had very
> little time in the real game, so expect rough edges. Bug reports are welcome.

## Read this first

- **It uses Natro Macro's open source route files.** The walks from the hive to each field and back
  are converted from [Natro Macro](https://github.com/NatroTeam/NatroMacro) (GPL-3.0). Thank you to
  the Natro team. See [NOTICE.md](NOTICE.md).
- **It is for macOS.** Natro is the Windows macro. HiveMac is a Mac app built the same way, not a port.
- **Automation is against Roblox's rules.** Accounts that use macros can be banned. Use it at your own
  risk, on an account you can afford to lose. HiveMac is not affiliated with Roblox or the game.

## What works today

| | |
|---|---|
| Fields | All 17 fields, each with its own minutes, backpack percent, pattern, size and sprinkler spot. Drag rows to reorder. |
| Runs | Save several named runs and switch between them. |
| Gathering loop | Reset to the hive, convert, walk to the field, gather until the backpack is full or time is up, walk back. |
| Screen reading | A few single pixels and small regions of the Roblox window: backpack bar, health bar, hive prompt. No full screen capture. |
| Stop key | One key (F9 by default) stops everything, even with Roblox in front. |
| Phone remote | Optional page on your Wi-Fi to start, pause and stop. |

**Saved but not run yet:** bug runs, planters, and the wealth clock and dispensers. You can set them up
in a run and HiveMac keeps their timers, but the macro does not carry them out yet. See
[docs/TODO.md](docs/TODO.md) for what is planned.

## Requirements

- macOS 14 or newer. Built and tested on Apple Silicon. Building from source needs Xcode 15 or newer.
- Roblox open, in a window or full screen (choose in the Macro tab). Camera mode Classic, movement
  mode Keyboard, low graphics set by hand, performance stats and micro profiler off, camera not
  inverted, English. Display colour profile sRGB, because the backpack reading expects it.
- In the game: the Red Cannon and the Glider (Mountain Top Shop, the upgrade of the Parachute) if you
  use cannon travel, and a sprinkler on your hotbar if you use one.

## Install

There is no download yet. Build it yourself:

```sh
git clone https://github.com/jonathanbrantner/HiveMac.git
cd HiveMac/swift
scripts/make-app.sh
open build/HiveMac.app        # or copy it to /Applications
```

On the first run macOS asks for **Screen Recording** and **Accessibility**. The gear at the top
right shows their state. **Input Monitoring** is only needed to record your own walks.

## Quick start

1. Open Roblox and stand in your hive.
2. **Calibrate** tab: press **Detect Roblox**.
3. **Macro** tab: hive colour, walk speed without buffs, travel, sprinkler and hotbar. Press Save.
4. **Fields** tab: choose your hive slot (1 to 6) and the fields, then press **Start**.

## If something goes wrong

| Problem | Try this |
|---|---|
| "Roblox was not found" | Open Roblox first, then press Detect Roblox. Check the window or full screen choice in the Macro tab. |
| Start does nothing or stops at once | Turn on Screen Recording and Accessibility for HiveMac in System Settings, then reopen the app. |
| The character walks the wrong way | Check your hive slot on the Fields tab, and your walk speed without buffs on the Macro tab. |
| Resets fail or loop | Stand in your hive, press Detect Roblox again, and see Advanced under Calibrate for the optional pictures. |
| Cannon travel fails | You need the Red Cannon and the Glider unlocked. Switch Default travel back to Walk to test. |

Still stuck? Open an issue. The template asks for the few details that help most.

## Uninstall

Quit HiveMac, delete `HiveMac.app`, and delete `~/Library/Application Support/HiveMac`. Then remove it
from the Privacy and Security lists in System Settings.

## For developers

```
swift/         the app (SwiftPM): HiveMacCore, HiveMacPlatform, HiveMacApp, tests
config/paths/  Natro's route files, converted (GPL-3.0 data)
tools/         the script that converted Natro's routes (only needed to redo that)
docs/          plans, research, live test checklist, TODO
```

```sh
cd swift && swift test
```

Work happens on `dev`. `main` takes pull requests once the checks pass.

## License

MIT for the HiveMac code. The route files in `config/paths/natro/` come from Natro Macro and stay
GPL-3.0. See [NOTICE.md](NOTICE.md).
