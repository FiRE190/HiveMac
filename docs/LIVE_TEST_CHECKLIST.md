# First live session

Nothing below can be done without the game open. Do it in this order and paste the
log (`logs/macro.log`) back when something misbehaves.

## Once, in Roblox and macOS

1. Roblox settings: camera mode Classic, movement mode Default (Keyboard), graphics
   manual at a low level, performance stats off, micro profiler off, camera not
   inverted, language English, background transparency 0.
2. Roblox in a **window**, not full screen, at a size you will keep. Resizing later
   is fine (everything is stored as fractions of the window) but the camera and
   recorded paths assume the same zoom and UI scale.
3. macOS: Screen Recording and Accessibility for the terminal you launch from.
   Display colour profile sRGB IEC61966-2.1.
4. In the game settings panel, read your walk speed. Enter it and your hive slot in
   the Settings tab, with your sprinkler type and hotbar key.

## Calibrate tab (about a minute)

5. Open Roblox in a window, then press **Detect Roblox**. Natro's default spots for the
   backpack bar, health bar and hive prompt are filled in automatically.
6. Read the **live readings** box. Gather a little by hand: the backpack percent should
   step up. If it says "not a bar colour" while the bar is filled, open **Adjust** and
   pick the backpack pixel (3 px inside the left end of the bar). Tell me the RGB if it
   still fails.
7. Optional, in **Adjust**: capture the hive prompt (drag a box around the E prompt while
   standing at the hive) and the hive view (after a reset). Without them the macro assumes
   it is at the hive after a reset.
8. Walks: nothing to do. Natro's default walks for all 17 fields are built in. Record your
   own only if one ends outside the field; it replaces the built in one.

## First runs

10. Fields tab: one field, sunflower, 2 minutes, 95 percent. Save. Start. Watch the
    first reset, convert and walk. F9 stops.
11. If the walk ends outside the field, record your own path: Calibrate tab,
    Prepare (reset), Start recording, walk there, Stop. Your file wins over the
    shipped Natro one.
12. Then longer runs, then a second field, then the cannon variant if you have the
    red cannon and the glider.

## What to send back

- `logs/macro.log` for the run.
- The Live readings text at the hive and in the field.
- Where the character ended up after a path replay (a screenshot is enough).
