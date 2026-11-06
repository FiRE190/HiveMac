# HiveMac to do

What is not built yet, in the order to build it. Everything here is OFF by default and code only
until it has been tried in the real game. Source of the inventory: Natro Macro (GPLv3). Game facts
(timers, field lists, planter numbers) are free to use. Natro's path and pattern files are not:
keep its notice on them and do not share this repo until that is handled.

## Run steps (settings already saved per run, engine missing)
- **Bug runs:** ladybug and rhino beetle first (every 330 s respawn), then spider (1830 s), mantis and
  scorpion (1230 s), werewolf (3630 s). Mobs are found by health bar colours 0x1fe744 and 0x6b131a.
  Also in the picker: coconut crab (36 h), king beetle (24 h), black bear quests.
- **Planters:** per slot a field and one of 12 planter types (bonus and growth hours per type).
  Manual mode first: fixed harvest interval per run. Placement needs the inventory drag, so it needs the game.
- **Quests:** last, hard. Needs quest log recognition.

## Easy additions (a route, a timer, an E prompt check)
Clock and dispensers, honeystorm, ant pass and robo pass: settings and timers are saved per run, the walking and E press are not built.
Still to list: field boosters (45 min), daily honey leaderboard.

## Port from the Python app
- Hive profile: field colour hints are in (community wiki data, only fields with a clear colour). Honey or minutes estimates are NOT built: no reliable rates are known.

## Future idea (not scoped, maybe too much for now)
A very simple website with just sign in and sign up, where you press Start and a few other basics to
control the macro from anywhere. Today the phone remote page covers this on the same Wi-Fi or Tailscale
without any account. A website would need a cloud relay between the site and the Mac, plus real auth.
Only worth it if the phone page is not enough.

## Checks
- Idle, window open, measured 2026-11-05: 30 MB real footprint, 0.0% CPU, 5 threads, 2.3 MB on disk (Python app: about 156 MB, 1.4% CPU, 60 MB on disk). Still to measure: while running a farm loop.
- First live session: `docs/LIVE_TEST_CHECKLIST.md`. Includes: does Esc R Enter empty the backpack?
