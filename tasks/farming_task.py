"""
Core farming loop:
  1. Move in configured pattern inside the field
  2. Hold click to collect pollen
  3. Detect backpack full → trigger HiveTask
  4. Detect death → trigger DeathRecoveryTask
  5. Heartbeat to keep watchdog satisfied
"""
import time
import threading

from tasks.base_task import BaseTask
from movement.movement_controller import get_movement_controller
from movement.patterns import PatternFactory
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
        self._hive_task_factory = None   # injected by FarmingService
        self._death_task_factory = None  # injected by FarmingService

    def set_hive_task_factory(self, factory) -> None:
        self._hive_task_factory = factory

    def set_death_task_factory(self, factory) -> None:
        self._death_task_factory = factory

    def run(self) -> None:
        cfg = get_config()
        sm = get_state()
        mc = get_movement_controller()

        threshold = self._profile.get("backpack_threshold_pct", 90)
        pattern_name = self._profile.get("movement_pattern", "circular")
        randomness = float(self._profile.get("randomness", 0.3))

        pattern = PatternFactory.create(
            pattern_name,
            radius=60,
            speed=1.0,
            randomness=randomness,
            waypoints=self._profile.get("waypoints", {}).get(
                self._profile.get("target_field", ""), []
            ),
        )

        log.info(
            "Farming '%s' with pattern '%s', threshold=%d%%",
            self._profile.get("target_field", "?"),
            pattern_name,
            threshold,
        )

        iter_count = 0
        for dx, dy in pattern.steps(max_steps=100000):
            if self._check_stop():
                break
            if not self._wait_resume():
                break

            sm.heartbeat()
            iter_count += 1

            # --- Death check (every 10 iters to avoid performance hit) ---
            if iter_count % 10 == 0 and is_dead():
                log.warning("Death detected during farming")
                sm.set(current_state=DEATH_RECOVERY)
                self._fsm.transition(DEATH_RECOVERY, force=True)
                if self._death_task_factory:
                    self._death_task_factory(self._profile).run()
                self._fsm.transition(FARMING, force=True)
                continue

            # --- Backpack check (every 5 iters) ---
            if iter_count % 5 == 0:
                pct = get_backpack_pct()
                sm.set(backpack_pct=pct)
                if pct >= threshold:
                    log.info("Backpack full (%d%%), heading to hive", pct)
                    self._fsm.transition(RETURNING_TO_HIVE)
                    if self._hive_task_factory:
                        self._hive_task_factory(self._fsm, self._profile).run()
                    self._fsm.transition(FARMING, force=True)
                    # Reset pattern after returning
                    pattern = PatternFactory.create(
                        pattern_name,
                        radius=60,
                        speed=1.0,
                        randomness=randomness,
                    )
                    continue

            # --- Movement step ---
            mc._press_direction(dx, dy, self._stop_event)

            # --- Pollen collection click ---
            hold_ms = cfg.get("timing.click_hold_ms", 120)
            import pyautogui
            pyautogui.mouseDown(button="left")
            human_sleep(hold_ms, 20)
            pyautogui.mouseUp(button="left")

            micro_pause(cfg.get("movement.micro_pause_chance", 0.08))
            human_sleep(cfg.get("timing.movement_loop_delay_ms", 80), 20)

        log.info("Farming task ended (iters=%d)", iter_count)
