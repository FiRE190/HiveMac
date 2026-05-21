"""
Death recovery: switch to backup field for 30 minutes, then return to original.
"""
import time

from tasks.base_task import BaseTask
from movement.movement_controller import get_movement_controller
from movement.patterns import PatternFactory
from movement.randomizer import human_sleep
from config.config_manager import get_config
from state.state_manager import get_state
from utils.logger import get_logger

log = get_logger(__name__)


class DeathRecoveryTask(BaseTask):
    def __init__(self, profile: dict) -> None:
        super().__init__("death_recovery")
        self._profile = profile

    def run(self) -> None:
        cfg = get_config()
        sm = get_state()
        mc = get_movement_controller()

        original_field = self._profile.get("target_field", "")
        backup_field = self._profile.get("backup_field", "Dandelion Field")
        recovery_min = cfg.get("death_recovery.backup_field_farming_min", 30)

        log.info(
            "DeathRecoveryTask: farming '%s' for %d min before returning to '%s'",
            backup_field, recovery_min, original_field,
        )

        # Wait for respawn
        human_sleep(4000, 500)

        # Navigate to backup field
        mc.navigate_to(backup_field, stop_event=self._stop_event, timeout_sec=60)
        human_sleep(1000, 200)

        # Farm backup field for configured duration
        sm.set(current_field=backup_field)
        pattern = PatternFactory.create(
            self._profile.get("movement_pattern", "circular"),
            radius=60,
            speed=1.0,
            randomness=float(self._profile.get("randomness", 0.3)),
        )

        import pyautogui
        start = time.time()
        for dx, dy in pattern.steps(max_steps=100000):
            if self._check_stop():
                break
            if time.time() - start >= recovery_min * 60:
                break
            if not self._wait_resume():
                break

            sm.heartbeat()
            mc._press_direction(dx, dy, self._stop_event)

            pyautogui.mouseDown(button="left")
            human_sleep(120, 20)
            pyautogui.mouseUp(button="left")
            human_sleep(80, 20)

        # Return to original field
        if original_field and not self._check_stop():
            log.info("DeathRecoveryTask: returning to original field '%s'", original_field)
            mc.navigate_to(original_field, stop_event=self._stop_event, timeout_sec=60)
            sm.set(current_field=original_field)

        log.info("DeathRecoveryTask complete")
