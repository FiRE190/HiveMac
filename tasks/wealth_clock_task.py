"""
Wealth Clock task:
  navigate → detect prompt → activate → optionally reset character → return
"""
import time

import pyautogui

from tasks.base_task import BaseTask
from movement.movement_controller import get_movement_controller
from movement.randomizer import human_sleep
from detection.wealth_clock_detector import is_wealth_clock_visible, is_wealth_clock_active
from state.fsm import FSM, WEALTH_CLOCK, FARMING
from state.state_manager import get_state
from utils.logger import get_logger

log = get_logger(__name__)

_ACTIVATE_KEY = "e"
_RESET_CMD = "/e dance"  # or character reset binding; configurable
_MAX_WAIT_SEC = 25


class WealthClockTask(BaseTask):
    def __init__(self, fsm: FSM, profile: dict) -> None:
        super().__init__("wealth_clock")
        self._fsm = fsm
        self._profile = profile

    def run(self) -> None:
        sm = get_state()
        mc = get_movement_controller()
        reset_char = self._profile.get("wealth_clock_reset_character", False)

        log.info("WealthClockTask: heading to wealth clock")
        sm.set(wealth_clock_count=sm.wealth_clock_count + 1)

        mc.navigate_to("wealth_clock", stop_event=self._stop_event, timeout_sec=45)

        # Wait for the activation prompt
        start = time.time()
        while not is_wealth_clock_visible():
            if self._check_stop():
                return
            if time.time() - start > _MAX_WAIT_SEC:
                log.warning("WealthClockTask: prompt not found, aborting")
                return
            human_sleep(400, 80)

        # Activate
        log.info("WealthClockTask: activating")
        pyautogui.press(_ACTIVATE_KEY)
        human_sleep(800, 100)

        # Optional character reset
        if reset_char:
            log.info("WealthClockTask: resetting character")
            pyautogui.hotkey("ctrl", "shift", "r")  # placeholder; user calibrates
            human_sleep(3000, 500)

        # Return to hive then field
        mc.navigate_to("hive", stop_event=self._stop_event, timeout_sec=40)
        human_sleep(500, 100)

        field = self._profile.get("target_field", "")
        if field:
            log.info("WealthClockTask: returning to '%s'", field)
            mc.navigate_to(field, stop_event=self._stop_event, timeout_sec=60)

        log.info("WealthClockTask complete")
