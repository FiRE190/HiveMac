# Changelog

## Unreleased

- Removed the older Python app. HiveMac is the native Swift app only.
- Drag to reorder, bug runs anywhere in a run, planter timers, hotbar section, simpler Calibrate.

## 0.2.0 (unreleased): native Swift app

- HiveMac is now a native Swift app (2 MB, about 30 MB of memory and 0% CPU idle, against about 156 MB and 1.4% for the Python app). The Python code stays in the repo.
- Same farming loop, Natro routes and patterns, pixel checks, convert loop, sprinkler and stop key (any key you choose, applies live).
- Run library: named runs, each with its own fields, minutes, backpack percent, return mode, travel, pattern and full per field options.
- Run extras saved per run: bug runs (pick mobs), planters (field and type per slot), clock and dispensers. Each mob and pickup has its own respawn timer, kept across restarts. The macro does not run these steps yet.
- App settings behind the gear: permissions, stop key, phone remote, updates, data folder. Update check against GitHub releases.
- Phone remote page (off by default, token link), watchdog, calibration tools (record a walk, capture pictures), field colour hints for your hive.
- 70 Swift tests, Swift CI job.

## 0.1.0 (unreleased)

- Return to the hive now defaults to walking, like Natro (all 17 walk back routes converted; the
  converter handles Natro's loops, hive slot switches and bee count branches). Reset stays a per field option.
- Hive profile defaults added (colour, bee count 50, average bee level, Cub Buddy, backpack percent).

First packaged version, rebuilt the Natro way.

- Loop: reset to the hive, convert, replay a recorded walk to the field, gather in a
  pattern until the backpack pixel reads full, repeat. Death takes the same path.
- Natro's default walks for 17 fields plus cannon variants, 12 gather patterns, sprinkler
  settings, a Fields tab and a one button Calibrate tab.
- Remote control page for a phone (status, log, start, pause, stop, settings).
- Permissions checked with native macOS calls; Start refuses with a plain reason.
- HiveMac.app bundle with its own icon and launcher, data in
  ~/Library/Application Support/HiveMac; install and release scripts; CI builds the bundle.
- 53 tests, lint and compile clean. Gathering costs about 0.1% of one core.
