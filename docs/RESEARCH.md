# Research: how Natro Macro and the other open macros actually work

Written 2026-11-05 from reading the source, not the READMEs. Natro Macro was cloned at
its current `main` (23,029 line `submacros/natro_macro.ahk` plus `lib/`, `paths/`,
`patterns/`, `submacros/background.ahk`). Line numbers below refer to that checkout.
The Existance macro (`existancepy/bss-macro-py`, Python, macOS) was cloned at its
2025-10-28 head. Nothing in this document was run against the game.

## 1. Short version

- Natro never walks back to the hive by default. It resets the character
  (`Esc`, `R`, `Enter`), waits for the empty health bar to appear and disappear,
  confirms it is standing at its hive by image, fixes the camera, converts, and walks
  to the next field from there. Every field path starts at the hive.
- All movement is open loop: hold a key for `4 * tiles / movespeed` seconds. The only
  closed loop part is optional haste compensation that reads the buff bar.
- The hive to field paths are tiny scripts (6 to 15 lines each) in `paths/gtf-*.ahk`.
  Gather patterns are the same kind of script in `patterns/*.ahk` and use four
  direction keys named relative to the field centre.
- Backpack fullness is one pixel read at a fixed offset from the window's top centre,
  decoded by a colour ladder into 5 percent steps, averaged over 6 samples at 1 Hz.
- Death is a template search for the "You died" text once per second from a separate
  process. Disconnects are a template search for the disconnect dialog every 250 ms
  while gathering.
- Everything is positioned relative to the Roblox client rect plus one vertical
  offset found by locating the pollen bar image once at start.
- The Existance macro proves the same design works on macOS with Python, `mss`,
  `pyautogui` and `cv2`. It copies Natro's backpack colour ladder verbatim, uses the
  red cannon for all travel, and recommends Roblox full screen with Game Mode off.
- On this Mac a 220x10 pixel `mss` grab costs 0.16 ms of CPU in our process (14 ms of
  wall time waiting on WindowServer). Pixel checks at a few Hz are effectively free.
  `opencv-python-headless` alone is 119 MB installed and takes 4.7 s to import; numpy
  plus Pillow plus mss plus pynput plus pyobjc Quartz is a 94 MB venv that imports in
  0.56 s with 27 MB resident.

## 2. Natro Macro, by question

### 2.1 Getting back to the hive: reset, not walk

`nm_Reset()` (`natro_macro.ahk:11043` to `11240`) is called before every field trip
from `nm_GoGather()` (`16522` to `16585`). The sequence inside the `while
(!HiveConfirmed)` loop:

1. Housekeeping before the reset: disconnect check, turn shift lock off
   (`nm_setShiftLock(0)`, image search for the shift lock icon at the bottom left,
   `11355`), close any open menu tab (`lib/nm_OpenMenu.ahk`), dismiss NPC dialog,
   yes/no prompts, feed window, blender and sticker screens, shop, generic close
   button, memory match. Each is a small image search in a fixed window region
   followed by a click. This is most of the function.
2. Park the mouse at `windowX+350, windowY+offsetY+100` (a neutral spot used
   everywhere, 34 occurrences) so the mouse is over the game and off any UI.
3. Set key delay to 250 ms plus the user's `KeyDelay` (default 20) and send
   `{Esc}{R}{Enter}` (`11180`). Roblox's menu has an "R to reset" shortcut; Enter
   confirms. The Existance macro sends the same with 250 to 400 ms gaps and repeats
   it twice for safety (`macro.py:1143` to `1150`).
4. Wait for the respawn by watching the health bar: loop up to 80 times with 100 ms
   sleeps; the counter `n` goes to 1 when the empty health bar image
   (`bitmaps["emptyhealth"]`, searched in the top 50 px of the window) or a grey
   dead health bar pixel appears, and to 2 when it disappears again (`11182` to
   `11188`). Then an extra `Sleep 2000 + 1000 * attempt` ("quick fix for laggy
   PCs"). `nm_HealthBar()` (`11240`) is one pixel at `windowX+windowWidth-75,
   windowY+36` checked for grey (each channel between 0x4D and 0x83).
5. Confirm position with `atHive()` (nested at `11229`): image search for the
   "collect/hey" hive prompt (`bitmaps["colhey"]`) in a 350x60 region at the top
   centre of the window. If that fails, `nm_DetectSpawn()` (`11261`) tilts the
   camera down and zooms in, searches the top quarter of the window for spawn pad
   bitmaps while rotating 180 degrees four times, and if found walks a hard coded
   move list `slotMove[HiveSlot]` (`1558`) to the player's hive slot. That is the
   "no hive claimed yet" case; with a claimed hive Roblox respawns you at your hive.
6. If `atHive()` succeeds it calls `nm_SetHiveCameraDirection(4)` (`11331`) to
   normalise the camera (see 2.3). `HiveConfirmed := 1` is set inside it.
7. Every 10th failed attempt it closes Roblox entirely (`CloseRoblox()`, `17591`)
   and lets `DisconnectCheck()` rejoin.
8. After the loop: `nm_convert()` (`17111`), then enforce a minimum delay since the
   reset was sent (`wait`, default 2000 ms, raised to 20 s when `youDied` was set
   because the game shows a longer death screen).

Walking back exists as an option (`FieldReturnType="walk"`, paths `paths/wf-*.ahk`,
`nm_walkFrom()` at `20520`), followed by `nm_findHiveSlot()` (`11615`) which holds
the left key for up to 15 s until the hive prompt appears, then steps right 1.5 tiles
at a time if it overran. Walk back is per field opt in; reset is the default and the
path the rest of the code assumes.

Also notable: the reset timestamp is posted to the background process so the death
detector ignores the "You died" text for 20 s after a deliberate reset
(`background.ahk nm_deathCheck`).

### 2.2 Walking from the hive to a field: recorded key scripts

- Files: `paths/gtf-<field>.ahk` (go to field, 17 fields), `paths/wf-<field>.ahk`
  (walk from field to hive), `gtp-*` (planters), `gtc-*` (collectables), `gtq-*`
  (quest givers), `gtb-*` (boosters). Loaded verbatim as text by `nm_importPaths()`
  (`307`) into `paths[kind][name]`.
- Format: plain AutoHotkey statements. Example `paths/gtf-sunflower.ahk`:

      nm_gotoramp()
      nm_Walk(9, BackKey)
      nm_Walk(6.75, BackKey, RightKey)
      send "{" RotRight " 2}"
      nm_Walk(29, RightKey)

  `nm_Walk(tiles, key1[, key2])` holds one or two keys for `tiles` tiles. One tile is
  4 studs (`lib/Walk.ahk:41`). `RotRight`/`RotLeft` are the `.` and `,` keys, one
  tap is 45 degrees (the hive search loop does `8/rotations*2` taps for two full
  turns, `11338`). `nm_gotoramp()` is the shared prefix: forward 5 tiles, then right
  `9.2*HiveSlot-4` tiles (`20365`), so the hive slot number only changes one lateral
  distance.
- Paths may branch on `MoveMethod = "Cannon"`: `paths/gtf-pineapple.ahk` either
  walks to the red cannon, presses E, holds a direction for a fixed time, double
  jumps (glider), and holds another direction, or walks the long way. Cannon
  timings are fixed sleeps (`HyperSleep(1850)`, `2750`, `1150`).
- Execution: `nm_createWalk(movement)` (`16960`) writes a complete new AutoHotkey
  script containing the key variables, `Walk()` and the path text, and launches it as
  a separate process. The child holds the virtual key `F14` down while it runs; the
  parent waits with `KeyWait "F14", "T120 L"` (2 minute cap) and kills the child with
  `nm_endWalk()`. The child releases every movement key on exit. That is their way
  of running a blocking key script while the main loop stays responsive. In Python a
  thread or an asyncio task with a stop event does the same job.
- Timing model, two variants chosen by `NewWalk`:
  - Legacy: `Walk(tiles) => HyperSleep(4000 / MoveSpeedNum * tiles)` ms
    (`16994`). `MoveSpeedNum` is the player's in game walk speed, default 28. So 9
    tiles is 1.29 s at speed 28.
  - New (default): `lib/Walk.ahk Walk(n)` integrates distance over time using
    `DetectMovespeed()`, which every iteration BitBlts a `windowWidth x 30` strip of
    the buff bar and image searches for haste, haste+, coconut haste, bear morph,
    oil and smoothie icons plus a stack digit, then applies the speed formula
    (`Walk.ahk:139`). It stops when integrated distance reaches `4n` studs. This is
    the expensive part of Natro and the part HiveMac can skip in version one.
- `nm_Move(ms, key1, key2)` (`17579`) is the older millisecond based hold used for
  sprinkler placement; `nm_setSprinkler()` (`17259`) has per field length/width
  tables scaled by `18/MoveSpeedNum`.

### 2.3 Camera and settings it forces

Natro does not have a one time "camera setup" routine; it normalises the camera every
time it is at the hive and after every pattern, and it relies on Roblox settings it
checks from the settings XML:

- `nm_MsgBoxIncorrectRobloxSettings()` (`2285`) reads `GlobalBasicSettings_*.xml`
  and demands: Graphics Quality manual and at level 3 ("lowest"), text size
  lowest, camera mode Classic (not Follow, so the camera does not swing with
  movement), movement mode Keyboard, camera not inverted, microprofiler off, and
  shift lock enabled in settings (the macro toggles it with Shift). It also warns if
  the window is full screen on UWP and if a touch screen is present.
- `GetYOffset()` (`lib/Roblox.ahk:50`) finds the vertical offset of the in game UI
  once per window handle by locating the pollen bar image in a 60x100 strip at the
  window's top centre; everything HUD related is `windowY + offsetY + constant`.
  Existance does the same with a honey bar bitmap (`robloxWindow.py:28`).
- Performance stats overlay: at every reset it image searches for "mem/cpu/gpu" text
  under the top bar and sends `Ctrl+F7` to hide it (`11084`).
- Camera at the hive: `nm_SetHiveCameraDirection(rotations)` (`11331`) image
  searches the bottom quarter of the window for hive bitmaps (`bitmaps["hive"]`,
  tolerance scaled by `windowWidth**2 // 3200`), rotating right by `rotations` taps
  up to two full turns and tilting down once halfway; when found it taps
  `RotRight 4` (180 degrees) so the player faces away from the hive, then
  `ZoomOut 5` (`O` key; zoom out is capped so extra taps are harmless). All paths
  assume this orientation and zoom.
- Camera in the field: per field `camera` direction and `turns` from the field
  defaults (`1572` onward, e.g. Blue Flower `Right`, 2) are sent after arrival and
  undone before walking back. Patterns may rotate the camera themselves through
  `nm_CameraRotation()` which records the net rotation and restores it on exit
  (`16880`).
- Walk scripts hold the mouse button down (`Click "Down"`) for the whole pattern
  cycle so the tool collects (`16659`); `DisableToolUse` turns that off.

### 2.4 Detection: what, where, how often

| What | Method | Where (relative to client rect, offsetY applied) | Rate |
|---|---|---|---|
| Backpack % | One pixel, colour ladder to 5 % steps, 6 sample rolling mean | `x = width/2 + 62`, `y = offsetY + 6` (`background.ahk nm_backpackPercent`) | 1 Hz, in `background.ahk` |
| Death | Template `died.png` tolerance 50, lower right quadrant | `background.ahk nm_deathCheck` | 1 Hz, suppressed 20 s after a reset and 10 s after a hit |
| At hive | Template "collect/hey" or "make honey"/"collect pollen" prompt | top centre `width/2-200 .. +400`, `offsetY .. +125` (`11252`, `11229`) | on demand |
| Hive position (camera) | Templates of hive pads, bottom quarter | `nm_SetHiveCameraDirection` | on demand |
| Respawn happened | Template `emptyhealth` or grey pixel in top 50 px | `11182` | 10 Hz during reset |
| Disconnected | Template `disconnected` in a 200x80 box at window centre | `DisconnectCheck`, `17614` | every 250 ms while gathering |
| Honey still rising | `PixelSearch` for 0xFFE280 in a 70x34 box left of the honey counter | `nm_activeHoney`, `18112` | 1 Hz while gathering and converting |
| Conversion done | `e_button` template gone or `hiveballoon` template present | `nm_convert`, `17111` | 1 Hz |
| Tokens | Not detected during gathering. Only `tokenlink` template in a 400x400 box bottom right during loot patterns (`nm_loot`, `17070`). Natro collects tokens by walking over them, not by seeing them | | |
| Night | Grass colour bitmaps in the bottom half, confidence counter | `background.ahk nm_CheckNight` | 1 Hz |
| Sprinkler for drift correction | Pinwheel template search from the window centre outward | `nm_LocateSprinkler`, `17482` | once per pattern cycle if enabled |

The backpack ladder is a nested if on the red channel then green/blue bounds of the
single pixel (`background.ahk:214` to `327`). The pixel sits 3 px into the bar which
is 220 px wide (11 px per 5 %). The Existance macro copied this ladder verbatim
(`submacros/backpack.py`), which is good evidence it transfers to macOS as long as the
display colour profile is sRGB (their docs insist on sRGB for exactly this reason).

### 2.5 Gather patterns

- Files: `patterns/*.ahk`: `Snake`, `XSnake`, `CornerXSnake`, `Lines`, `Slimline`,
  `Squares`, `Diamonds`, `Fork`, `Auryn`, `SuperCat`, `e_lol`, `Stationary`.
- Keys are abstract: `TCFBKey` (toward centre, forward/back axis), `AFCFBKey`
  (away from centre), `TCLRKey`, `AFCLRKey`. `nm_GoGather` binds them to WASD
  according to per field `invertFB`/`invertLR` flags (`16620`), so one pattern
  file serves every field.
- Variables available: `size` (XS 0.25, S 0.5, M 1, L 1.5, XL 2), `reps`
  (the "width" setting), `facingcorner`, `A_Index` for the loop counter, and all
  field settings. Walk lengths are expressions in tiles, e.g. Squares:

      loop reps {
        send "{" TCFBKey " down}"
        Walk(5 * size + A_Index)
        send "{" TCFBKey " up}{" TCLRKey " down}"
        ...
      }

- Cadence: one pattern file is one "cycle". `nm_gather()` (`16847`) starts the walk
  child once and sends `F13` to run another cycle. Between cycles the parent polls
  every 50 ms: disconnect/death/night every 250 ms, backpack and inactive honey and
  boost state every 1 s, quest state every 5 s (`16660` to `16760`). Backpack
  interrupt fires when the filtered percent is at least `FieldUntilPack - 2` (and
  tries the micro converter hotkey first if configured). Interrupts that are not
  death or disconnect wait for the cycle to finish (`KeyWait "F14", "T180 L"`) when
  the pattern carries `;@NoInterrupt`.
- Field defaults (`nm_importFieldDefaults`, `1572`): pattern, size, width, camera
  direction and turns, sprinkler corner and distance, backpack percent (95), gather
  minutes (10), return type, drift check, shift lock, invert flags. Sunflower is
  `CornerXSnake`, M, width 4, no camera turn, sprinkler Upper Left distance 8,
  invertLR 1, return Walk.
- Start position in field: `nm_setSprinkler()` walks from the arrival point to the
  chosen corner using per field length/width constants scaled by `18/MoveSpeedNum`,
  places the sprinkler (hotbar `1`, jump timing adjusted by image feedback), and the
  pattern starts from there.
- Field drift compensation (`17434`): after every cycle, find the sprinkler on
  screen and press keys until it is back inside a central box. Needs the Supreme
  Saturator's blue colour. Optional.

### 2.6 Failure handling

- Stuck or frozen game: `nm_activeHoney()` returns 0 when the honey counter is not
  changing; 30 consecutive seconds of that while the backpack is below target sets
  `interruptReason := "Inactive Honey"` and increments `GameFrozenCounter`. Three
  strikes closes Roblox (`11047`). There is no position based stuck detection.
- Did not reach the hive after reset: retry; every 10th attempt restarts Roblox.
- Did not reach the cannon or a planter: image check for the prompt, step back 1.5
  tiles up to 9 times, else reset and start over (`nm_gotoCannon`, `11534`;
  `nm_searchForE`, `18143`).
- Death: background sets `youDied`; the gather loop breaks within 250 ms, keys are
  released, the normal reset path runs with a 20 s minimum wait. Mondo and Coconut
  Crab deaths skip that field next time (`11058`).
- Disconnect: `DisconnectCheck()` (`17614`) closes Roblox and relaunches through a
  `roblox://placeID=1537690962&linkcode=...` deep link (private server) or the
  public place id, waits up to 4 min for a window, 3 min for the loading screen, 3
  min for the loaded game, rotates through fallback servers, then `nm_claimHiveSlot()`
  (`17915`) walks to the configured slot from spawn and presses E, with an optional
  hive slot detection that reads six fixed pixels for the red "unclaimed" tint.
- Watchdog: `submacros/Heartbeat.ahk` pings the main, status and background scripts
  every 5 s and kills and restarts the whole macro (and Roblox) if any has not
  answered for 120 s or no Roblox window existed for 10 min.
- Key safety: every walk child releases all movement keys, space and E on exit;
  `stop()` sends key up for WASD and space and mouse up.

### 2.7 Windows specific pieces and macOS equivalents

| Natro piece | What it does | macOS equivalent |
|---|---|---|
| `WinExist("Roblox ahk_exe RobloxPlayerBeta.exe")`, `WinGetClientPos`, `WinActivate` | find, measure, focus the window | `CGWindowListCopyWindowInfo` (Quartz, no Accessibility needed) or the existing AppleScript in `calibration/roblox_finder.py`; `NSRunningApplication.activateWithOptions_` or `open -a Roblox` to focus |
| GDI `BitBlt`/`Gdip_BitmapFromScreen` | capture a region | `mss` (wraps `CGWindowListCreateImage`) or the Quartz call directly; measured 0.16 ms CPU per small grab |
| `Gdip_ImageSearch` with tolerance, `PixelSearch`, `PixelGetColor` | template and pixel checks | numpy comparisons on the grabbed array; a tolerance template search is a few lines of numpy for templates this small (most Natro bitmaps are under 40x20 px) |
| `Send "{sc011 down}"` scan codes, `SetKeyDelay` | key input | `pynput` or `pyautogui` (both post `CGEvent`s); Existance uses pyautogui and works. Rotate camera `,` `.`, zoom `i` `o`, tilt `pageup` `pagedown` |
| AutoHotkey child process per walk, `F13`/`F14`/`F16` virtual keys for control | run a blocking key script without blocking the UI | a Python thread with `threading.Event` for stop and pause |
| `OnMessage`/`PostMessage` between scripts, `IniWrite` for shared state | inter process messaging | plain in process objects; one process is enough |
| `Run "roblox://..."` deep link | rejoin a server | `open "roblox://placeID=1537690962..."` works on macOS (Existance `appManager.openDeeplink`) |
| `Ctrl+F7` performance stats toggle, `Esc R Enter` reset, `Esc L Enter` leave | Roblox shortcuts | same keys on the Mac client (Existance uses the same reset keys) |
| Registry read of Roblox settings XML | verify game settings | not available; the Mac client stores `GlobalBasicSettings_13.xml` under `~/Library/Roblox/` on some versions, but checking it is optional. Verify visually at session start instead (pollen bar found, backpack pixel readable) |
| `timeBeginPeriod` high resolution sleep | sub ms timing | `time.perf_counter` plus `time.sleep`; macOS sleeps are already fine grained |
| UWP and touchscreen checks | | not applicable |

## 3. The Existance macro (Python on macOS): what differs from Natro and what to copy

Source: `src/modules/macro.py` (3,934 lines), `controls/keyboard.py`,
`screen/screenshot.py`, `submacros/backpack.py`, `paths/*.py`, `settings/patterns/*.py`.

- Same skeleton: reset to hive, convert, cannon to field, pattern, backpack pixel.
  Patterns and paths are Python snippets run with `exec` inside the class, so
  Natro `.ahk` patterns can be converted (`submacros/convertAhkPattern.py`).
- Travel is cannon first. `cannon()` (`macro.py:1238`) walks right from the hive by
  `1.2 * hiveNumber + attempt` seconds, jumps on the pad, then looks for the cannon
  prompt; `paths/cannon_to_field/<field>.py` are 8 to 15 lines of camera taps, `E`,
  a held direction, two space taps (glider) and sleeps. Their docs state the only in
  game requirements are the red cannon and the hang glider.
- Reset confirmation differs: after the health bar check it grabs a 200x10 strip at
  the bottom centre of the window and masks white respawn pad and blue balloon
  colours in HLS (`macro.py:132` to `137`, `1178` to `1200`), spinning 180 degrees up
  to four times, then presses `o` eight times to zoom out fully. If still not at the
  hive it walks `w 5`, `s 0.55`, then sideways `1.32 s * |hive_number - 3|`.
- Walk timing: `keyboard.walk(key, t)` holds for `t * 28 / movespeed` seconds
  (`keyboard.py:60`); optional haste compensation via template matching the buff bar
  (`hasteCompensation.py`, cv2). Speed unit is seconds at walk speed 28, not tiles.
- Window and scale: expects Roblox full screen (`isFullScreen`, `toggleFullScreen`
  with `Cmd+Ctrl+F`, `macro.py:519` to `555`), the menu bar set to auto hide in full
  screen, and on Apple Silicon macOS 14 to 15 it clicks the Game Mode toggle off
  from the menu bar at start (`startDetect`, `3799`). It detects Retina by grabbing a
  150 px region and checking whether `mss` returns 300 px. HUD offsets are
  hardcoded constants in points (e.g. backpack pixel `mx + mw//2 + 62`, `my +
  yOffset + 6`, `macro.py:575`) scaled by a per resolution fudge table
  (`screenData.py`). That table is a sign that fixed offsets without a calibration
  step get fragile across displays; a calibration wizard that records the pixel is
  the cleaner answer.
- Capture: `mss` region grabs with `mss.darwin.IMAGE_OPTIONS = 0`, and a fallback to
  the `screencapture` CLI because for some users `mss` took "almost a minute" in a
  child process (`screenshot.py:19`). Worth remembering if captures ever stall:
  keep capture in the main process.
- Input: `pyautogui.keyDown/keyUp` with a `keyUp('fn')` before every key down because
  the Fn modifier sometimes stuck (`keyboard.py:111`). Mouse hold uses both pynput
  and pyautogui.
- Death: template of the blue "died" text (`blueTextImageSearch("died")`,
  `macro.py:1534`) in a background loop. Night: grass colour in the bottom half.
- OCR: uses Apple's Vision framework through `ocrmac` when available, else
  PaddleOCR or EasyOCR, for reading the text next to the E prompt and the honey
  counter. HiveMac does not need OCR for the core loop; Natro has none.
- System settings their docs require: Roblox camera Classic, movement Default
  (Keyboard), full screen on, performance stats off, micro profiler off, camera not
  inverted, UI navigation toggle on, language English, background transparency 0;
  macOS display colour profile sRGB IEC61966-2.1, ABC keyboard input source, menu
  bar auto hide in full screen, Game Mode off, "close windows when quitting" off,
  and the Roblox "scale to fit below built-in camera" Finder option on notch Macs.
- Size: 296 PNG templates, cv2, PaddleOCR or EasyOCR, `eel` (Chrome based GUI),
  Discord bot, streaming. Far above HiveMac's budget; the techniques transfer, the
  dependency list does not.

## 4. Other open macros on GitHub (only what differs)

- `nosyliam/revolution-macro` (174 stars, "Windows and macOS"): the repository holds
  only release binaries, ONNX models (`token_detection`, `vic_detection`,
  `sprinkler`, OCR) and update manifests. No source. The idea it adds is neural
  token and sprinkler detection plus graph pathfinding without resets. Out of scope.
- `painvision/BeeTuxMacro` (Linux, shell with `wtype`/`wlrctl`/`grim`/ImageMagick):
  backpack check is one pixel tested for a red range in a loop
  (`check_inventory.sh`), with a pure time limit as fallback mode. Paths are shell
  functions of `sleep` and key holds. Shows the minimum viable version: pixel plus
  timer plus key holds.
- `fenixJK/Aurex` (C++ and Qt, Windows and macOS, no stars yet): Lua path and
  pattern files; requires macOS 14+ and Screen Recording and Accessibility. Nothing
  read beyond the README.
- `Yoon-robin/Beolkkuri` (Python, macOS and Windows, Korean UI, React front end):
  installer needs 3 GB; feature list mirrors Natro. Not read.
- `thebest12dev/zepton` (C++): Windows only so far, Linux via `ydotool`, "very
  early". Nothing to take.
- `ru3tyYT/duckbooster`, `GXX0T/MacroFox`, `susalmon/Boost-Macro`: hotbar boosting
  helpers, not farming loops.
- `FaethyvveIcye/bss` (AHK): function library, same techniques as Natro.

## 5. HiveMac's own history

Commits in order (`git log --reverse --stat`):

1. `ddabebd` (May 21) initial project: FSM, threaded farming loop, five geometric
   patterns yielding (dx, dy) offsets converted to key presses by
   `movement/movement_controller.py`, OCR backpack reading (Tesseract), full screen
   template matching for hive and death, a `coordinates.json` of named screen points
   and `route_<dest>` lists for `navigate_to()`, wealth clock and mob run timers,
   death recovery that farms a backup field for 30 min, F9 stop, watchdog.
2. `2aca68e`, `d69b31b` (May 21): setup wizard, drag region picker, checklist,
   AppleScript Roblox window finder, relative coordinates, hive calibrator
   (template, amber colour, proximity), validation gate on Start.
3. `3717df8` (May 21): adaptive movement controller using Lucas Kanade optical flow
   to measure speed, burst key holds, stuck detection by flow, speed calibration by
   holding W for 2 s.
4. `bee269f` (Nov 5, previously unpushed work): the navigation stack: `nav_map.json`
   with 18 nodes and 33 edges derived from Natro tile data at an assumed 16 studs
   per second, route graph and planner, landmark localisation with HSV fallbacks,
   checkpoint and temporal validators, recovery arbiter and manager, world model
   beliefs, perception fusion, cannon and glider controllers, telemetry, debugger.
   About 11,500 lines.
5. `676b06d`, `b86db2d` (Nov 5): license, lint, 16 tests, CI, README; the farming
   loop wired end to end on paper (stop reaches children, keys released, reset uses
   `Esc R Enter`, template capture saves the dragged box).

What is in the working tree today: 113 Python files, 18,287 lines. `cv2` is imported
by 10 files (detection, perception, navigation landmarks, optical flow, calibration).
`pyautogui`/`pynput` by 15 files despite `execution/input_interface.py` being
declared the single owner. The two templates on disk (`templates/hive_ui.png`,
`respawn_screen.png`) are 2.8 and 3.0 MB full screen captures, so they are not usable
templates. `config/settings.json` has every region at zero and `scale_factor 1.0`.
`config/coordinates.json` has a few recorded points from May.

What the Natro style loop needs from this code base:

- Keep: the CustomTkinter control panel and log console, profile manager, FSM and
  state manager, watchdog and F9 stop, `roblox_finder.py` (AppleScript bounds),
  region picker and wizard shell, `input_interface.py` as the one input owner,
  logger, tests and CI.
- Replace: `tasks/farming_task.py` (optical flow bursts) with a pattern cycle runner;
  `tasks/hive_task.py` and `death_recovery_task.py` with one reset to hive routine;
  `detection/backpack_detector.py` (HSV area ratio over a user drawn region) with the
  Natro pixel ladder at a calibrated point; `death_detector.py` and
  `hive_detector.py` (full screen cv2 matching) with small region checks.
- Drop: `navigation/` (route graph, localisation, recovery, arbiter, telemetry),
  `world_model/`, `planning/`, `perception/`, `observability/`, the adaptive and
  optical flow movement, `movement/patterns.py` geometric generators,
  `glider_controller.py` and `cannon_controller.py` in their current form, the OCR
  module, `nav_map.json` and `routes.json`. None of it is needed once every trip
  starts at the hive and the only closed loop checks are "am I at the hive" and
  "is the backpack full". The 16 studs per second assumption in `nav_map.json` is
  also wrong against Natro's own default of 28, so the timings would need redoing
  anyway.

## 6. Measurements on this Mac (Apple M6, 24 GB, macOS 27.2, 2560x1440 display)

Scratch virtual environments built with Homebrew Python 3.12 in the session
scratchpad (not in the repo):

| Set | Installed size | Import time | Resident after import |
|---|---|---|---|
| numpy, Pillow, mss, pynput, pyobjc-framework-Quartz | 94 MB venv (numpy 34, Pillow 13, objc 11, PyObjCTest 16 which can be deleted, pip 12) | 0.56 s | 27 MB |
| numpy, opencv-python-headless 5.0 | 166 MB venv (cv2 alone 119 MB) | 4.66 s | 49 MB, and OpenCL reports enabled |

Capture cost, 220x10 px region (the backpack bar), 100 iterations after warm up:

| Method | Wall per grab | CPU in our process per grab |
|---|---|---|
| `mss` | 14.5 ms | 0.16 ms |
| `Quartz.CGWindowListCreateImage` direct | 12.9 ms | 0.14 ms |

A 1280x720 grab was 17.7 ms wall, so the cost is a fixed WindowServer round trip,
not pixel count. At 2 to 4 Hz the capture CPU in our process is under 0.1 percent of a
core; the WindowServer side will show in `top` under WindowServer, not under Python.
The current repo venv contains only pytest and ruff (44 MB, Python 3.15, so the
runtime deps were never installed into it; the launcher pins 3.10 to 3.12 for cv2).

The wheel sizes from PyPI for the record: opencv-python 48 MB download, numpy 12 MB,
Pillow 4.9 MB, pyobjc-core 6.7 MB, mss 0.1 MB, pynput 0.1 MB, pyautogui 0.1 MB,
customtkinter 0.3 MB.

## 7. What this means for the redesign

- Reset to hive is the backbone. Field to hive paths, localisation, recovery levels
  and the route graph go away. The loop is: confirm at hive, convert, play the
  recorded hive to field script, run pattern cycles until the backpack pixel says
  full or the timer expires, reset, repeat. Death lands on the same path.
- Open loop timing is enough. Natro's legacy mode is `4000 / movespeed * tiles` ms,
  Existance is `t * 28 / movespeed` seconds. Store the player's walk speed (from the
  in game settings panel) and scale every recorded hold. Haste compensation can be
  added later if drift is a problem; corner aligned patterns are the first defence.
- Pixel checks first, templates second. Backpack: one pixel, Natro's ladder, 6 sample
  mean, 1 Hz. Health bar grey pixel for the respawn wait. "At hive" and "disconnect"
  are the two places a small template is justified; both are tiny crops in fixed
  regions. No OCR, no optical flow.
- The window and the UI offset are the two calibrations everything depends on.
  Natro and Existance both locate the pollen bar once to find `offsetY`. The wizard
  should: find the Roblox window (AppleScript or Quartz), find the pollen bar (or ask
  the user to click it), derive the backpack pixel and the health bar pixel from it,
  let the user verify with a live readout, and record hive to field key sequences
  with timings.
- Windowed vs full screen is a real decision. Natro is windowed (its only hard
  requirement is height of at least 500 px). Existance is full screen on macOS and
  fights Game Mode. HiveMac already finds window bounds, so windowed at a fixed size
  is the simpler path and keeps the control panel visible. Jonathan should pick one
  and keep it fixed; recorded paths only replay correctly with the same camera and
  window.
- Camera: Classic camera mode, zoomed fully out (press `o` five to eight times), and
  the hive facing fix after every reset are what make recorded paths repeatable.
  The hive facing fix needs one small template or colour check of the hive row; the
  Existance bottom strip colour mask is the cheaper of the two.
- Dependencies: numpy, Pillow, mss, pynput (or pyautogui), customtkinter, pyobjc
  Quartz. Drop opencv, Tesseract, pyautogui's helper packages if pynput covers the
  input, and the perception stack. That lands the venv near 90 MB and the import
  under one second, within the 200 MB and 150 MB resident targets with room for the
  UI.

## 8. Open items that need Jonathan

Collected here so the next step can ask once:

1. Windowed Roblox at a fixed size and position, or full screen? (Research leans
   windowed; see section 7.)
2. Roblox settings to set once: camera mode Classic, movement Keyboard, graphics
   manual at the lowest level, performance stats and micro profiler off, camera not
   inverted, language English, background transparency 0, shift lock allowed.
   macOS: display colour profile sRGB, Game Mode off if full screen is chosen.
3. Walk speed number from the in game settings panel (Natro default 28).
4. Hive slot number (1 to 6, counted from the ramp) and whether the red cannon and
   glider are unlocked (decides whether cannon paths are even an option).
5. Which fields to farm first (one is enough to prove the loop).
6. Live sessions: run the wizard (window, pollen bar, backpack pixel, health pixel,
   hive view), record one hive to field walk per field, then a supervised loop.
7. Whether an earlier automator outside this repo exists; if so, its location (asked
   once, not assumed).
