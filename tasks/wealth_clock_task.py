"""
WealthClockTask: navigate → detect prompt → activate → optionally reset character → return.

Navigation uses RouteManager (→ Navigator → NavMap).
"""
import time

import pyautogui

from tasks.base_task import BaseTask
from navigation.route_manager import get_route_manager
from movement.randomizer import human_sleep
from detection.wealth_clock_detector import is_wealth_clock_visible
from state.fsm import FSM
from state.state_manager import get_state
from utils.logger import get_logger

log = get_logger(__name__)

_ACTIVATE_KEY  = "e"
_MAX_WAIT_SEC  = 25


class WealthClockTask(BaseTask):
    def __init__(self, fsm: FSM, profile: dict) -> None:
        super().__init__("wealth_clock")
        self._fsm     = fsm
        self._profile = profile

    def run(self) -> None:
        sm  = get_state()
        rm  = get_route_manager()
        reset_char = self._profile.get("wealth_clock_reset_character", False)

        log.info("WealthClockTask: heading to wealth clock")
        sm.set(wealth_clock_count=sm.wealth_clock_count + 1)

        result = rm.execute("wealth_clock", self._stop_event)
        if result.outcome.name == "FAILED":
            log.warning("WealthClockTask: failed to reach wealth clock")
            return

        # Wait for the activation prompt
        start = time.time()
        while not is_wealth_clock_visible():
            if self._check_stop():
                return
            if time.time() - start > _MAX_WAIT_SEC:
                log.warning("WealthClockTask: prompt not visible after %.0fs", _MAX_WAIT_SEC)
                return
            human_sleep(400, 80)

        log.info("WealthClockTask: activating")
        pyautogui.press(_ACTIVATE_KEY)
        human_sleep(800, 100)

        if reset_char and not self._check_stop():
            log.info("WealthClockTask: resetting character")
            pyautogui.hotkey("ctrl", "shift", "r")
            human_sleep(3000, 500)

        if self._check_stop():
            return

        hive_node = self._profile.get("hive_node", "hive_1_entrance")
        rm.execute(hive_node, self._stop_event)
        human_sleep(500, 100)

        field = self._profile.get("target_field", "")
        if field and not self._check_stop():
            log.info("WealthClockTask: returning to '%s'", field)
            rm.execute(field, self._stop_event)

        log.info("WealthClockTask complete")
