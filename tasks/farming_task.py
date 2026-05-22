"""
Core farming loop — hybrid adaptive movement.

Movement is driven by AdaptiveController (real-time optical-flow feedback loop)
rather than fixed timers or blind waypoint scripts.  The controller:
  - adjusts burst duration based on live speed measurement vs. base_speed
  - detects and corrects field boundary crossings
  - recovers from stuck states (walls, lag) automatically

Backpack and death checks remain on their iteration cadence and are
entirely independent of the movement layer.
"""
import time
import threading

import pyautogui

from tasks.base_task import BaseTask
from movement.adaptive_controller import AdaptiveController
from movement.randomizer import human_sleep, micro_pause
from detection.backpack_detector import get_backpack_pct
from detection.death_detector import is_dead
from config.config_manager import get_config
from state.state_manager import get_state
from state.fsm import FSM, RETURNING_TO_HIVE, DEATH_RECOVERY, FARMING
from utils.logger import get_logger

log = get_logger(__name__)


class FarmingTask(BaseTask):
    def __init__(self, fsm: FSM, profile: dict) -> None:
        super().__init__("farming")
        self._fsm = fsm
        self._profile = profile
        self._hive_task_factory  = None
        self._death_task_factory = None

    def set_hive_task_factory(self, factory) -> None:
        self._hive_task_factory = factory

    def set_death_task_factory(self, factory) -> None:
        self._death_task_factory = factory

    def run(self) -> None:
        cfg = get_config()
        sm  = get_state()
        ac  = AdaptiveController()

        threshold    = self._profile.get("backpack_threshold_pct", 90)
        pattern_name = self._profile.get("movement_pattern", "circular")

        log.info(
            "Farming '%s' with adaptive pattern '%s', threshold=%d%%",
            self._profile.get("target_field", "?"),
            pattern_name,
            threshold,
        )

        # Auto-calibrate speed if not yet measured (2-second W-press before farming)
        if ac.get_base_speed() == 0:
            log.info("No base speed cached — running quick auto-calibration")
            sm.heartbeat()
            ac.calibrate_speed(self._stop_event)

        iter_count = 0

        for key, weight in ac.pattern_cycle(pattern_name):
            if self._check_stop():
                break
            if not self._wait_resume():
                break

            sm.heartbeat()
            iter_count += 1

            # ── Death check (every 10 steps) ──────────────────────────────────
            if iter_count % 10 == 0 and is_dead():
                log.warning("Death detected during farming")
                sm.set(current_state=DEATH_RECOVERY)
                self._fsm.transition(DEATH_RECOVERY, force=True)
                if self._death_task_factory:
                    self._death_task_factory(self._profile).run()
                self._fsm.transition(FARMING, force=True)
                # Discard stale optical-flow history from before death
                ac.reset()
                continue

            # ── Backpack check (every 5 steps) ────────────────────────────────
            if iter_count % 5 == 0:
                pct = get_backpack_pct()
                sm.set(backpack_pct=pct)
                if pct >= threshold:
                    log.info("Backpack full (%d%%), heading to hive", pct)
                    self._fsm.transition(RETURNING_TO_HIVE)
                    if self._hive_task_factory:
                        self._hive_task_factory(self._fsm, self._profile).run()
                    self._fsm.transition(FARMING, force=True)
                    # Player has teleported back to field — reset flow history
                    ac.reset()
                    continue

            # ── Adaptive movement step ────────────────────────────────────────
            result = ac.step(key, weight, self._stop_event)

            if result.was_stuck:
                log.debug(
                    "Movement stuck (key=%s ratio=%.2f conf=%.2f)",
                    result.key, result.speed_ratio, result.confidence,
                )
            elif result.corrected:
                log.debug(
                    "Overshoot corrected (key=%s ratio=%.2f)",
                    result.key, result.speed_ratio,
                )

            # ── Pollen collection hold ────────────────────────────────────────
            hold_ms = cfg.get("timing.click_hold_ms", 120)
            pyautogui.mouseDown(button="left")
            human_sleep(hold_ms, 20)
            pyautogui.mouseUp(button="left")

            micro_pause(
                cfg.get("movement.micro_pause_chance", 0.08),
                cfg.get("movement.micro_pause_min_ms", 50),
                cfg.get("movement.micro_pause_max_ms", 250),
            )

        log.info("Farming task ended (steps=%d)", iter_count)
