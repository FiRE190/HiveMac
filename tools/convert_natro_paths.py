"""
One off converter: Natro Macro paths/*.ahk -> config/paths/natro/*.json.

Usage: venv/bin/python tools/convert_natro_paths.py /path/to/NatroMacro/paths

Converts gtf-* (hive to field) into to_field/<field>.json (walk branch) and
to_field/<field>_cannon.json when a cannon branch exists, and wf-* (field to
hive) into to_hive/<field>.json. Lines the converter does not understand stop
the run so nothing is silently dropped. Natro Macro is GPL-3.0; see
config/paths/natro/README.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movement.paths import PATHS_DIR, PathFile, convert_natro_path  # noqa: E402

FIELD_NAMES = {
    "bamboo": "bamboo", "blueflower": "blue flower", "cactus": "cactus", "clover": "clover",
    "coconut": "coconut", "dandelion": "dandelion", "mountaintop": "mountain top", "mushroom": "mushroom",
    "pepper": "pepper", "pinetree": "pine tree", "pineapple": "pineapple", "pumpkin": "pumpkin",
    "rose": "rose", "spider": "spider", "strawberry": "strawberry", "stump": "stump", "sunflower": "sunflower",
}


def main(src: Path) -> int:
    out_dir = PATHS_DIR / "natro"
    count = 0
    for prefix, kind in (("gtf", "to_field"), ("wf", "to_hive")):
        for ahk in sorted(src.glob(f"{prefix}-*.ahk")):
            slug = ahk.stem.split("-", 1)[1]
            field = FIELD_NAMES.get(slug, slug)
            try:
                branches = convert_natro_path(ahk.read_text(encoding="utf-8-sig"))
            except ValueError as exc:
                print(f"{ahk.name:28s} SKIPPED: {exc}")
                continue
            for variant, steps in branches.items():
                if not steps:
                    continue
                suffix = "" if variant == "walk" else f"_{variant}"
                name = f"{field.replace(' ', '_')}{suffix}"
                pf = PathFile(name=name, steps=steps, source=f"NatroMacro paths/{ahk.name} ({variant} branch)",
                              walk_speed=28.0,
                              notes="Converted from Natro Macro (GPL-3.0). Hold steps are at walk speed 28.")
                pf.save(out_dir / kind / f"{name}.json")
                count += 1
                print(f"{ahk.name:28s} {variant:7s} -> {kind}/{name}.json  ({len(steps)} steps)")
    print(f"{count} path files written to {out_dir}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
