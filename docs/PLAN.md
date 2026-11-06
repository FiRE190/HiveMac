# Plan

Written 2026-11-05. The Python app mentioned below has since been removed; its numbers are kept as the
baseline the Swift app was measured against. What is done, what is not proven, and what comes next, in order.

## Done

**Research** (`docs/RESEARCH.md`): how Natro Macro works from its source (reset to hive,
recorded key paths, colour pixel checks, failure handling), plus the Existance macOS
macro and other open macros, with measurements on this Mac.

**The macro, rebuilt the Natro way.** Reset to the hive, convert, replay a walk to the
field, gather in a pattern until the backpack pixel says full, repeat. Death takes the
same path as any reset. The whole loop runs in tests against a simulated game.

**Features you asked for**
- Natro's default walks for all 17 fields, plus 12 cannon variants, built in. Your own
  recorded walks replace them per field.
- Twelve gather patterns with size, width and invert options, and Natro's per field defaults.
- Sprinkler type (none, basic, silver, golden, diamond, supreme), start corner and distance.
- Settings tab: walk speed, hive slot, sprinkler, default travel, windowed or full screen,
  wait times.
- Remote control from a phone: a link with a token shows status and log, and can start,
  pause, stop and edit settings and fields.
- A short Fields tab and a one button Calibrate tab (Detect Roblox, then live readings).

**Permissions.** Read with the real macOS calls. Start is refused with a plain reason when
key presses or screen reading would silently fail. F9 is skipped with a warning when Input
Monitoring is off.

**App packaging, modelled on Lanes.** `scripts/make-app.sh`, `install.sh`, `release.sh`,
a generated icon, an Info.plist with version, an ad hoc signature, a small native launcher
so macOS lists permissions under "HiveMac". Settings, profiles, logs, templates and
recordings live in `~/Library/Application Support/HiveMac`, not inside the app. Built a
60 MB bundle, linted it, confirmed the signature stays valid after running, launched it
and saw it start and write its data folder.

**Quality.** 53 tests, lint and compile clean. Gathering costs 0.11% of one core, waiting
0.05%, 46 MB for the engine, 79 MB with the window open.

## Not proven yet

- **Anything in the real game.** Roblox is not installed on this Mac. Layout guesses (the 28
  point title bar, Natro's default pixel spots, the hive prompt check) are unverified.
- **Permissions under the app.** I expect macOS to list permissions under HiveMac because
  the launcher is the bundle's process, but I could not click through the prompts. If it
  lists Python instead, grant that one.
- **Idle cost with the window open.** Measured 1.5% before I cut redraws and polling. The
  new number was not taken. Rerun `tools/measure_cpu.py` and watch Activity Monitor.
- **The phone page in a real phone browser.** Tested with curl and in unit tests only.
- **Rebuilds reset permissions.** The ad hoc signature changes every build, so macOS may ask
  again after each install.

## Next, in order

1. **Finish the app packaging.** Add the Lanes style CI job (build the bundle, lint the
   plist, verify the signature, check the icon), a changelog, the Install and Uninstall
   sections in the README, drop test files from the bundled environment, run `install.sh`
   once. Optional: a self signed local certificate so permissions survive rebuilds.
2. **First live session** (after installing Roblox), using `docs/LIVE_TEST_CHECKLIST.md`:
   grant permissions to HiveMac, Detect Roblox, check the readings, run one field for
   2 minutes with the Stop button ready, send back the log. Fix whatever the first run shows.
3. **Make it hold up for hours.** Disconnect detection and rejoin, a hive slot claim after
   rejoin, stuck detection from the honey counter like Natro, a screenshot on error.
4. **Walk speed under haste.** Only if live runs show drift: sample the buff bar and scale
   walk time, the way Natro's walk does.
5. **Comfort.** Start at login, a menu bar status item, phone notifications on death or
   stop, scheduling, more fields per profile.
6. **Distribution, only if you want it.** A standalone Python so the zip runs without
   Homebrew, and notarization, which needs a paid Apple developer account. I will not
   spend money without asking.

## Decisions for you

- Windowed or full screen Roblox. It is a setting, default windowed.
- Whether HiveMac should be shared at all. If yes, `config/paths/natro/` is GPL data from
  Natro Macro and needs its notice kept; the rest is MIT.

## Baseline: Python app, window open, idle (measured by Jonathan, Activity Monitor, 2026-11-05)

Compare the Swift app against these numbers.

| Process | CPU % | Threads | Idle wake ups | Memory |
|---|---|---|---|---|
| HiveMac (Python, pid 29570) | 1.4 | 9 | 0 | 143.4 MB |
| AutoFill (HiveMac) (macOS helper for text fields) | 0.0 | 5 | 0 | 10.4 MB |
| HiveMac (launcher, pid 29569) | 0.0 | 1 | 0 | 2.1 MB |
| **Total** | **1.4** | **15** | **0** | **about 156 MB** |

Targets from the plan: under 1% CPU waiting, under 150 MB resident. The Python app is over both
with the window open. (Gathering with the window closed measured 0.11% earlier, so the window
and Tk redraws are the cost.)

## Resource budget (Jonathan, 2026-11-05)

**Hard ceiling: 0.5 GB of RAM while running, all processes of the app counted.** Our own
targets are tighter so there is room to spare: under 100 MB for the Swift app, under 1% CPU
waiting, near zero GPU. The Python app (about 156 MB with the window open) is the reference.

Measured on this Mac (M6, macOS 27.2), Swift native layer, `swift/Sources/hivemac-probe`:

| What | Result |
|---|---|
| 50 screen reads (ScreenCaptureKit, 1 pixel and 400x120 regions) | 0.02 s of CPU in total, 20 MB peak memory |
| Wall time per read | about 33 ms (waiting on the system, not our CPU); the deprecated CoreGraphics route is about 16 ms |
| At 3 reads per second | roughly 0.1% of one core |

ScreenCaptureKit is kept (the supported API). If the reads ever need to be cheaper, one capture
of a thin top strip per second can serve both the backpack and health pixels.


## Swift app idle measurement (2026-11-05)

| | Python app | Swift app |
|---|---|---|
| Memory, window open | about 156 MB | 30 MB (footprint) |
| CPU, idle | 1.4% | 0.0% |
| On disk | 60 MB | 2.3 MB |

Measured with `footprint` and `top` on the installed bundle. Not yet measured while farming.
