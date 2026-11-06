# Paths converted from Natro Macro

These JSON files were produced by `tools/convert_natro_paths.py` from the
`paths/gtf-*.ahk` and `paths/wf-*.ahk` files of Natro Macro
(https://github.com/NatroTeam/NatroMacro), which is licensed under the GNU GPL
v3.0. They are key sequences and distances, kept here as a starting point so the
macro has a path for every field on day one. The rest of HiveMac is MIT licensed;
treat this folder as GPL-3.0 derived data.

Record your own walks with the wizard's path recorder; files in
`config/paths/user/` take priority over these.

Conventions: `walk` steps are in tiles (4 studs) and scale with your walk speed.
`hold` steps are seconds at walk speed 28 (the cannon and glider branches) and
are rescaled at run time. `gotoramp` expands to Natro's "forward 5, right
9.2 * hive slot - 4" prefix for your hive slot.
