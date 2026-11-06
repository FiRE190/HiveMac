"""
The farming loop: reset to the hive, convert, travel, gather, repeat, rotating
through the enabled fields. Death and a lost screen both fall back to the reset,
which is the only recovery there is, as in Natro.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from macro.game import FieldConfig, Game, GatherResult


@dataclass
class LoopStats:
    cycles: int = 0
    converts: int = 0
    deaths: int = 0
    resets: int = 0
    failed_resets: int = 0
    last_result: str = ""
    history: list[GatherResult] = field(default_factory=list)


class FarmLoop:
    def __init__(self, game: Game, fields: list[FieldConfig], on_stats: Callable[[LoopStats], None] | None = None,
                 max_failed_resets: int = 3, max_cycles: int | None = None) -> None:
        self.game = game
        self.fields = [f for f in fields if f.enabled]
        self.stats = LoopStats()
        self._on_stats = on_stats or (lambda s: None)
        self._max_failed = max_failed_resets
        self._max_cycles = max_cycles
        self._index = 0

    def next_field(self) -> FieldConfig:
        f = self.fields[self._index % len(self.fields)]
        self._index += 1
        return f

    def run(self) -> str:
        """Returns why the loop ended: stopped, no_fields, reset_failed, cycles_done."""
        g = self.game
        if not self.fields:
            g.status("error", "no enabled fields")
            return "no_fields"
        after_death = False
        while not g.stopped:
            if self._max_cycles is not None and self.stats.cycles >= self._max_cycles:
                return "cycles_done"
            fcfg = self.next_field()
            self.stats.resets += 1
            if not g.reset_to_hive(after_death=after_death):
                if g.stopped:
                    break
                self.stats.failed_resets += 1
                self._on_stats(self.stats)
                if self.stats.failed_resets >= self._max_failed:
                    g.status("error", "giving up after repeated reset failures")
                    g.release_everything()
                    return "reset_failed"
                continue
            self.stats.failed_resets = 0
            after_death = False
            if g.convert():
                self.stats.converts += 1
            if g.stopped:
                break
            if not g.travel_to(fcfg):
                continue
            result = g.gather(fcfg)
            self.stats.cycles += 1
            self.stats.last_result = result.reason
            self.stats.history.append(result)
            if result.reason == "death":
                self.stats.deaths += 1
                after_death = True
            self._on_stats(self.stats)
            if result.reason in ("backpack", "time") and fcfg.return_method == "walk":
                if g.walk_back(fcfg):
                    if g.convert():
                        self.stats.converts += 1
                    # the loop still resets before the next field; that is the cheap
                    # way to keep the camera and position known
        g.release_everything()
        return "stopped"
