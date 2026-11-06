"""
Path and pattern steps.

A path is a list of steps saved as JSON. The same Step type drives gather
patterns and hive to field walks, so one runner (Walker.run_steps) executes both.

Step types:
  walk    keys=["w"] or ["w","d"], tiles=9        hold keys for a distance
  hold    keys=[...], seconds=1.85                 hold keys for a fixed time (cannon, glider)
  rotate  direction="left"|"right", count=2        camera yaw, 45 degrees per tap
  tap     key="e", count=1                         press a key
  wait    seconds=0.5
  zoom    direction="out"|"in", count=5
  mouse   direction="down"|"up"

Pattern steps may use the abstract keys tc_fb, afc_fb, tc_lr, afc_lr (toward or
away from the field centre, forward/back or left/right axis). They are bound to
WASD per field with `bind_pattern_keys`.

`gotoramp` is a special step kept symbolic in path files because its distance
depends on the hive slot: expand_path() turns it into walks for a given slot.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable, Iterator

PATHS_DIR = Path(__file__).resolve().parent.parent / "config" / "paths"
USER_PATHS_DIR = PATHS_DIR / "user"

ABSTRACT_KEYS = ("tc_fb", "afc_fb", "tc_lr", "afc_lr")
NATRO_KEYS = {"FwdKey": "w", "BackKey": "s", "LeftKey": "a", "RightKey": "d",
              "TCFBKey": "tc_fb", "AFCFBKey": "afc_fb", "TCLRKey": "tc_lr", "AFCLRKey": "afc_lr"}


@dataclass
class Step:
    type: str
    keys: list[str] = field(default_factory=list)
    tiles: float = 0.0
    seconds: float = 0.0
    direction: str = ""
    key: str = ""
    count: int = 1

    @staticmethod
    def walk(keys: Iterable[str] | str, tiles: float) -> "Step":
        keys = [keys] if isinstance(keys, str) else list(keys)
        return Step("walk", keys=keys, tiles=float(tiles))

    @staticmethod
    def hold(keys: Iterable[str] | str, seconds: float) -> "Step":
        keys = [keys] if isinstance(keys, str) else list(keys)
        return Step("hold", keys=keys, seconds=float(seconds))

    @staticmethod
    def rotate(direction: str, count: int = 1) -> "Step":
        return Step("rotate", direction=direction, count=int(count))

    @staticmethod
    def tap(key: str, count: int = 1) -> "Step":
        return Step("tap", key=key, count=int(count))

    @staticmethod
    def wait(seconds: float) -> "Step":
        return Step("wait", seconds=float(seconds))

    @staticmethod
    def zoom(direction: str, count: int) -> "Step":
        return Step("zoom", direction=direction, count=int(count))

    @staticmethod
    def mouse(direction: str) -> "Step":
        return Step("mouse", direction=direction)

    @staticmethod
    def gotoramp() -> "Step":
        return Step("gotoramp")

    def to_dict(self) -> dict:
        d = {"type": self.type}
        if self.keys:
            d["keys"] = list(self.keys)
        if self.tiles:
            d["tiles"] = self.tiles
        if self.seconds:
            d["seconds"] = self.seconds
        if self.direction:
            d["direction"] = self.direction
        if self.key:
            d["key"] = self.key
        if self.count != 1:
            d["count"] = self.count
        return d

    @staticmethod
    def from_dict(d: dict) -> "Step":
        s = Step(type=str(d["type"]))
        s.keys = list(d.get("keys", []))
        s.tiles = float(d.get("tiles", 0.0))
        s.seconds = float(d.get("seconds", 0.0))
        s.direction = str(d.get("direction", ""))
        s.key = str(d.get("key", ""))
        s.count = int(d.get("count", 1))
        return s


@dataclass
class PathFile:
    name: str
    steps: list[Step]
    source: str = ""
    walk_speed: float = 28.0       # speed the `hold` steps were recorded at
    notes: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "source": self.source, "walk_speed": self.walk_speed,
                "notes": self.notes, "steps": [s.to_dict() for s in self.steps]}

    @staticmethod
    def from_dict(d: dict) -> "PathFile":
        return PathFile(name=d["name"], steps=[Step.from_dict(s) for s in d.get("steps", [])],
                        source=d.get("source", ""), walk_speed=float(d.get("walk_speed", 28.0)),
                        notes=d.get("notes", ""))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=1), encoding="utf-8")

    @staticmethod
    def load(path: Path) -> "PathFile":
        return PathFile.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def gotoramp_steps(hive_slot: int) -> list[Step]:
    """Natro nm_gotoRamp: forward 5 tiles, then right 9.2*slot-4 tiles (slot 1..6)."""
    slot = min(6, max(1, int(hive_slot)))
    return [Step.walk("w", 5), Step.walk("d", 9.2 * slot - 4)]


def expand_path(steps: Iterable[Step], hive_slot: int) -> list[Step]:
    out: list[Step] = []
    for s in steps:
        if s.type == "gotoramp":
            out.extend(gotoramp_steps(hive_slot))
        else:
            out.append(s)
    return out


def bind_pattern_keys(invert_fb: bool = False, invert_lr: bool = False) -> dict[str, str]:
    """Natro nm_GoGather: TC = toward centre, AFC = away from centre."""
    return {
        "tc_fb": "s" if invert_fb else "w",
        "afc_fb": "w" if invert_fb else "s",
        "tc_lr": "d" if invert_lr else "a",
        "afc_lr": "a" if invert_lr else "d",
    }


def scale_holds(steps: Iterable[Step], recorded_speed: float, actual_speed: float) -> list[Step]:
    """Rescale `hold` steps recorded at one walk speed to the player's speed.
    `walk` steps are in tiles and scale at run time already."""
    from movement.walk import key_duration_at_speed
    out = []
    for s in steps:
        if s.type == "hold" and s.keys and set(s.keys) & {"w", "a", "s", "d"}:
            out.append(Step.hold(s.keys, key_duration_at_speed(s.seconds, recorded_speed, actual_speed)))
        else:
            out.append(s)
    return out


def total_seconds(steps: Iterable[Step], speed: float) -> float:
    """Rough duration estimate for logging and timeouts."""
    t = 0.0
    for s in steps:
        if s.type == "walk":
            t += s.tiles * 4.0 / max(1.0, speed)
        elif s.type in ("hold", "wait"):
            t += s.seconds
        elif s.type in ("rotate", "tap", "zoom"):
            t += 0.06 * s.count
    return t


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def field_slug(field_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", field_name.strip().lower()).strip("_")


def find_path_file(kind: str, field_name: str, variant: str = "walk") -> Path | None:
    """kind: 'to_field' or 'to_hive'. variant: 'walk' or 'cannon'. User files win."""
    slug = field_slug(field_name)
    suffix = "" if variant == "walk" else f"_{variant}"
    for base in (USER_PATHS_DIR, PATHS_DIR / "natro"):
        p = base / kind / f"{slug}{suffix}.json"
        if p.exists():
            return p
    return None


def list_fields_with_paths(kind: str = "to_field") -> list[str]:
    names: set[str] = set()
    for base in (USER_PATHS_DIR, PATHS_DIR / "natro"):
        d = base / kind
        if d.exists():
            for p in d.glob("*.json"):
                names.add(p.stem.replace("_cannon", ""))
    return sorted(names)


# ---------------------------------------------------------------------------
# Natro .ahk path conversion (the simple subset used by paths/*.ahk)
# ---------------------------------------------------------------------------

_RE_WALK = re.compile(r"nm_Walk\(\s*([0-9.*+\-/ ()]+?)\s*,\s*(\w+Key)\s*(?:,\s*(\w+Key))?\s*\)", re.I)
_RE_ROT = re.compile(r'\{\s*"?\s*(RotRight|RotLeft|ZoomOut|ZoomIn)\s*"?\s*(\d+)?\}', re.I)
_RE_BAREWALK = re.compile(r"^Walk\(\s*([0-9.*+\-/ ()]+?)\s*(?:,\s*\d+\s*)?\)\s*$")
_RE_SLEEP = re.compile(r"(?:HyperSleep|Sleep)\s*\(?\s*(\d+)\s*\)?", re.I)
_RE_KEYDOWN = re.compile(r'\{\s*"?\s*(\w+)\s*"?\s+down\}', re.I)
_RE_KEYUP = re.compile(r'\{\s*"?\s*(\w+)\s*"?\s+up\}', re.I)
_RE_SPACE = re.compile(r'send\s+"\{space(?:\s+(\d+))?\}"', re.I)


def _natro_key(name: str) -> str:
    for k, v in NATRO_KEYS.items():
        if k.lower() == name.lower():
            return v
    return name.lower()


def _eval_number(expr: str) -> float:
    if not re.fullmatch(r"[0-9.*+\-/ ()]+", expr):
        raise ValueError(f"unsafe expression {expr!r}")
    return float(eval(expr, {"__builtins__": {}}, {}))  # noqa: S307 arithmetic only, validated above


def convert_natro_path(text: str) -> dict[str, list[Step]]:
    """Convert the body of a Natro paths/*.ahk file.

    Returns {"walk": steps} and, when the file has an `if (MoveMethod = "Cannon")`
    branch, also {"cannon": steps}. Unknown lines raise ValueError so nothing is
    silently dropped.
    """
    branches: dict[str, list[Step]] = {}
    current = "walk"
    pending: list[Step] = []
    held: list[str] = []

    def flush_hold(seconds: float) -> None:
        if held:
            pending.append(Step.hold(list(held), seconds))
        else:
            pending.append(Step.wait(seconds))

    for raw in text.splitlines():
        line = raw.split(";", 1)[0].strip().lstrip("﻿")
        if not line:
            continue
        low = line.lower()
        if low.startswith("if") and "cannon" in low:
            branches.setdefault("cannon", [])
            current, pending, held = "cannon", branches["cannon"], []
            continue
        if low.startswith("} else") or low == "else {" or low == "else":
            branches.setdefault("walk", [])
            current, pending, held = "walk", branches["walk"], []
            continue
        if line in ("}", "{"):
            continue
        branches.setdefault(current, pending if pending is not None else [])
        pending = branches[current]
        if low.startswith("nm_gotoramp"):
            pending.append(Step.gotoramp())
            continue
        if low.startswith("nm_gotocannon"):
            pending.append(Step("gotocannon"))
            continue
        m = _RE_WALK.search(line)
        if m:
            keys = [_natro_key(m.group(2))] + ([_natro_key(m.group(3))] if m.group(3) else [])
            pending.append(Step.walk(keys, _eval_number(m.group(1))))
            continue
        m = _RE_BAREWALK.match(line)
        if m:
            tiles = _eval_number(m.group(1))
            if held:
                pending.append(Step.walk(list(held), tiles))
            else:
                pending.append(Step.wait(tiles * 4.0 / 28.0))
            continue
        # one line may carry several send tokens: "{e up}{LeftKey down}" etc.
        handled = False
        for m in _RE_ROT.finditer(line):
            name, n = m.group(1), int(m.group(2) or 1)
            if name.lower().startswith("rot"):
                pending.append(Step.rotate("right" if "right" in name.lower() else "left", n))
            else:
                pending.append(Step.zoom("out" if "out" in name.lower() else "in", n))
            handled = True
        for m in _RE_KEYDOWN.finditer(line):
            k = m.group(1)
            key = _natro_key(k)
            if key == "e":
                pass  # the E press is emitted on its key up
            else:
                held.append(key)
            handled = True
        for m in _RE_KEYUP.finditer(line):
            k = m.group(1)
            key = _natro_key(k)
            if key == "e":
                pending.append(Step.tap("e"))
            elif key in held:
                held.remove(key)
            handled = True
        for m in _RE_SPACE.finditer(line):
            pending.append(Step.tap("space", int(m.group(1) or 1)))
            handled = True
        m = _RE_SLEEP.search(line)
        if m and not handled:
            flush_hold(int(m.group(1)) / 1000.0)
            handled = True
        elif m and handled:
            flush_hold(int(m.group(1)) / 1000.0)
        if not handled:
            raise ValueError(f"cannot convert line: {raw!r}")
    return branches


def iter_steps(pf: PathFile, hive_slot: int, actual_speed: float) -> Iterator[Step]:
    for s in scale_holds(expand_path(pf.steps, hive_slot), pf.walk_speed, actual_speed):
        yield s
