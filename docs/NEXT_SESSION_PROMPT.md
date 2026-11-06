# HiveMac: make it actually work, the Natro way, and keep it small

You are working in `~/Projects/Other/HiveMac` (GitHub: FiRE190/HiveMac, private). It is a
macOS Python macro for Bee Swarm Simulator (Roblox): screen capture + template/colour
detection, keyboard and mouse input, a CustomTkinter control panel. It has never run end to
end. On 2026-11-05 a full code pass fixed about 20 breaks (see the commit "Wire the farming
loop end to end" and `docs/`), there are 16 pytest tests, lint and CI are green, and the README
lists what still needs the real game. Work happens on branch `dev`; `main` only takes PRs.
Start by reading README.md, `main.py`, `services/farming_service.py`, `tasks/`, and
`config/nav_map.json`, then `git log --reverse --stat` to see how the original
BeeSwarmLocalMacro (the first 4 commits) worked before the navigation stack was added.
If Jonathan had an earlier automator outside this repo, ask him for its location once; do not
guess.

## Step 1: research (read-only, write findings to docs/RESEARCH.md before changing code)

1. **Natro Macro** (https://github.com/NatroTeam/NatroMacro, AutoHotkey, Windows, open
   source). Clone it into the scratchpad and read the actual source, not the README. Answer
   concretely, with file references:
   - How it gets back to the hive: it resets the character (Bee Swarm respawns you at your
     hive) instead of walking back. Where in the code, what key sequence, how it waits.
   - How it walks from the hive to each field: recorded key-press sequences with timings,
     per field, from a known camera setup. Where those sequences live and their format.
   - The camera/zoom setup it forces before anything else (and the game settings it needs:
     graphics, FOV, UI scale) so the screen looks the same every time.
   - How it detects backpack fullness, the hive, death/respawn, and tokens: pixel colour
     checks at fixed coordinates vs image search; thresholds; how often it checks.
   - Gather patterns per field (shapes, widths, "walk then gather" cadence) and the
     settings it exposes for them.
   - How it handles failure: stuck detection, reconnects, the watchdog/"reset on error".
   - Anything that depends on Windows (AutoHotkey, Roblox window handle, DirectX) that
     must be replaced on macOS, and what the macOS equivalent is.
2. **HiveMac's own history**: what the first version did (coordinate walker, templates),
   what the later navigation stack added (route graph, landmark localisation, recovery),
   and which of that is needed once "reset to hive" replaces walking back.
3. **Other open-source BSS macros on GitHub** (search; several exist): note only
   techniques that differ from Natro.

## Step 2: redesign for simplicity, then implement

Based on the research, propose (as a plan Jonathan approves) a simpler loop in the Natro
style, then build it:

- Session start: force the camera/zoom setup, verify the HUD regions, stand at the hive.
- Go to field: play a recorded key sequence for that field (hive -> field only, never
  field -> hive).
- Gather: a pattern from a small set (Natro's shapes), with timed key holds and clicks.
- Backpack full: reset character, wait for respawn at the hive, convert, walk to field
  again. Death is handled by the same path (you are at the hive anyway).
- Checks by pixel colour at fixed, calibrated coordinates where possible; template
  matching only where colour is ambiguous. Capture only the small regions you need, at
  the rate you need (a few Hz), not full screens in a loop.
- Keep the calibration wizard for: Roblox window bounds, display scale, backpack region,
  the hive/respawn check pixels, and a "record key sequence" tool so Jonathan can record
  hive -> field walks himself.
- Delete or quarantine what the simpler loop does not need (the navigation/perception/
  world_model/planning stack can stay in git history; do not carry dead code).

## Efficiency and size targets (measure, don't assume)

- CPU: under 3% of one core while gathering, under 1% while waiting. Use `top -l` and
  `sample` to prove it; report before/after.
- RAM: under 150 MB resident. Check with `footprint <pid>`.
- GPU: zero. No GPU work at all (no OpenCL/Metal paths in OpenCV; avoid cv2 if numpy +
  Pillow + mss can do the pixel checks, since opencv-python alone is ~100 MB installed).
- Disk/size: the installed app plus venv under 200 MB; `requirements.txt` pinned; no
  Tesseract, no OCR.
- Only capture screen regions, never the full screen in the hot loop; reuse buffers.

## Working rules

- Do all research and coding that needs no one at the keyboard first, then give Jonathan ONE
  list of what needs him (game settings to set, sequences to record, live test sessions).
- Never run the macro against the game yourself; Jonathan runs live tests and pastes logs.
- Commit on `dev` in small, described commits; open one PR to `main` when a milestone works.
  Keep ruff, compileall and pytest green; add tests for every pure function you write.
- Plain language in docs and commits, no dashes used as punctuation.
- Do not spend money or install paid tools without asking.
