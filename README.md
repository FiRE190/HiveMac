# HiveMac

[![check](https://github.com/FiRE190/HiveMac/actions/workflows/check.yml/badge.svg)](https://github.com/FiRE190/HiveMac/actions/workflows/check.yml)
![status: beta](https://img.shields.io/badge/status-beta-f2b134)
![macOS 14+](https://img.shields.io/badge/macOS-14%2B-lightgrey)

A small, native macOS app that farms **Bee Swarm Simulator** (Roblox) for you. Pick the fields,
how long to stay on each, and press Start.

> **Beta.** It builds, passes its tests and runs against a simulated game, but it has had very
> little time in the real game. Expect rough edges. Bug reports are welcome.

## Good to know first

- **Uses Natro Macro's open source route files.** The walks from the hive to every field (and back)
  are converted from [Natro Macro](https://github.com/NatroTeam/NatroMacro) (GPL-3.0). Thank you to
  the Natro team. See [NOTICE.md](NOTICE.md).
- **For macOS only** (14 or newer, Apple Silicon or Intel). Natro is the Windows macro; HiveMac is
  its Mac counterpart, not a port.
- **Automation is against Roblox's rules.** Accounts that use macros can be banned. Use it at your
  own risk and on an account you can afford to lose. HiveMac is not affiliated with Roblox or the
  game's developers.

## What it does

- **Fields.** Any of the 17 fields, each with its own minutes, backpack percent, pattern, size and
  sprinkler spot. Drag the rows to put them in order.
- **Runs.** Save several named runs ("Strawberry grinder", "Pine night") and switch between them.
- **Between fields.** Bug runs (pick the mobs), planters (field and planter type per slot), and the
  wealth clock and dispensers. These are saved with the run; the macro does not carry them out yet.
- **Reads the screen like Natro does.** A few single pixels and small regions of the Roblox window:
  backpack bar, health bar, the hive prompt. No full screen captures in the loop.
- **Small.** About 30 MB of memory and about 0.1% CPU while idle.
- **Phone remote.** Optional: open a link on your phone (same Wi-Fi) to start, pause and stop.
- **Stop key.** One key (F9 by default) stops everything, even when Roblox is in front.

## In the game you need

Roblox in a window, the Red Cannon and the Glider (Mountain Top Shop, the upgrade of the Parachute)
if you use cannon travel, a sprinkler on your hotbar if you use one, and your hive slot (1 to 6)
set in HiveMac. The Calibrate tab has a Detect Roblox button; press it with Roblox open.

## Install

There is no download yet. Build it yourself (needs Xcode 15 or newer):

```sh
git clone https://github.com/FiRE190/HiveMac.git
cd HiveMac/swift
scripts/make-app.sh
open build/HiveMac.app            # or copy it to /Applications
```

On the first run macOS asks for **Screen Recording** and **Accessibility** (gear at the top right
shows the state). **Input Monitoring** is only needed if you want to record your own walks.

## Using it

1. Open Roblox in a window and stand in your hive.
2. **Calibrate** tab: press **Detect Roblox**.
3. **Macro** tab: your hive colour, walk speed (no buffs), travel, sprinkler and hotbar.
4. **Fields** tab: choose your hive slot and the fields. Press **Start**.

## Uninstall

Quit HiveMac, delete `HiveMac.app`, and delete `~/Library/Application Support/HiveMac`.
Remove it from the Privacy & Security lists in System Settings.

## Layout

```
swift/            the app (SwiftPM): HiveMacCore, HiveMacPlatform, HiveMacApp, tests
config/paths/     Natro's route files, converted (GPL-3.0 data)
tools/            the script that converted Natro's routes (Python, only needed to redo that)
docs/             plans, research, live test checklist, TODO
```

## Development

```sh
cd swift && swift test
```

Work happens on `dev`; `main` takes pull requests once the checks pass.

## License

MIT for the HiveMac code. The route files in `config/paths/natro/` are derived from Natro Macro and
stay GPL-3.0. See [NOTICE.md](NOTICE.md).
