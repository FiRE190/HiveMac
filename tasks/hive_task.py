"""
HiveTask: navigate to hive → activate conversion → hold key until empty → return.

Navigation uses RouteManager (→ Navigator → NavMap) — the ONLY path for
inter-node travel.  The old coordinate-walker is not used here.
"""
import time

import pyautogui

from tasks.base_task import BaseTask
from navigation.route_manager import get_route_manager
from navigation.navigator import get_navigator
from movement.randomizer import human_sleep
from detection.hive_detector import is_at_hive, is_hive_converting
from detection.backpack_detector import get_backpack_pct
from state.fsm import FSM, CONVERTING_POLLEN, FARMING
from utils.logger import get_logger

log = get_logger(__name__)

_CONVERT_KEY      = "e"
_MAX_HIVE_WAIT    = 30     # seconds to wait for hive UI after arriving
_MAX_CONVERT_SEC  = 120    # safety cap on conversion loop


class HiveTask(BaseTask):
    def __init__(self, fsm: FSM, profile: dict) -> None:
        super().__init__("hive")
        self._fsm     = fsm
        self._profile = profile

    def run(self) -> None:
        rm = get_route_manager()

        hive_node = self._profile.get("hive_node", "hive_1_entrance")
        log.info("HiveTask: navigating to '%s'", hive_node)

        result = rm.execute(hive_node, self._stop_event)
        if not result.confirmed and result.outcome.name == "FAILED":
            log.warning("HiveTask: failed to reach hive — aborting conversion")
            return

        # Wait for hive proximity UI
        start = time.time()
        while not is_at_hive():
            if self._check_stop():
                return
            if time.time() - start > _MAX_HIVE_WAIT:
                log.warning("HiveTask: hive UI not detected after %.0fs", _MAX_HIVE_WAIT)
                return
            human_sleep(300, 50)

        self._fsm.transition(CONVERTING_POLLEN)
        log.info("HiveTask: converting pollen")

        # Hold convert key until backpack visual reads empty
        start = time.time()
        while time.time() - start < _MAX_CONVERT_SEC:
            if self._check_stop():
                break

            pct = get_backpack_pct()
            if pct == 0:
                log.info("HiveTask: backpack empty")
                break

            pyautogui.keyDown(_CONVERT_KEY)
            human_sleep(400, 80)
            pyautogui.keyUp(_CONVERT_KEY)
            human_sleep(200, 50)

        human_sleep(500, 100)

        # Return to the assigned field via nav stack
        field = self._profile.get("target_field", "")
        if field and not self._check_stop():
            log.info("HiveTask: returning to '%s'", field)
            rm.execute(field, self._stop_event)
