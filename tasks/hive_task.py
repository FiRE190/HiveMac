"""
Hive task: navigate to hive → wait for conversion UI → hold key until empty → return to field.
"""
import time

from tasks.base_task import BaseTask
from movement.movement_controller import get_movement_controller
from movement.randomizer import human_sleep
from detection.hive_detector import is_at_hive, is_hive_converting
from detection.backpack_detector import get_backpack_pct
from state.fsm import FSM, CONVERTING_POLLEN, FARMING
from utils.logger import get_logger

log = get_logger(__name__)

_CONVERT_KEY = "e"
_MAX_HIVE_WAIT_SEC = 30
_MAX_CONVERT_SEC = 120


class HiveTask(BaseTask):
    def __init__(self, fsm: FSM, profile: dict) -> None:
        super().__init__("hive")
        self._fsm = fsm
        self._profile = profile

    def run(self) -> None:
        mc = get_movement_controller()
        log.info("HiveTask: navigating to hive")

        mc.navigate_to("hive", stop_event=self._stop_event, timeout_sec=45)

        # Wait for hive UI to appear
        start = time.time()
        while not is_at_hive():
            if self._check_stop():
                return
            if time.time() - start > _MAX_HIVE_WAIT_SEC:
                log.warning("HiveTask: timed out waiting for hive UI")
                return
            human_sleep(300, 50)

        self._fsm.transition(CONVERTING_POLLEN)
        log.info("HiveTask: converting pollen")

        # Hold convert key until backpack empty
        import pyautogui
        start = time.time()
        while time.time() - start < _MAX_CONVERT_SEC:
            if self._check_stop():
                break

            pct = get_backpack_pct()
            if pct == 0:
                log.info("HiveTask: backpack empty, done")
                break

            pyautogui.keyDown(_CONVERT_KEY)
            human_sleep(400, 80)
            pyautogui.keyUp(_CONVERT_KEY)
            human_sleep(200, 50)

        human_sleep(500, 100)

        # Return to the assigned field
        field = self._profile.get("target_field", "")
        if field:
            log.info("HiveTask: returning to '%s'", field)
            mc.navigate_to(field, stop_event=self._stop_event, timeout_sec=60)
