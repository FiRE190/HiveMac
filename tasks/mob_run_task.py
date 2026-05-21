"""
Mob Run task:
  iterate configured mob route → defeat mobs → collect tokens → return to field

Retry logic: if stuck (no mobs cleared after timeout), retry up to max_retries times.
"""
import time

import pyautogui

from tasks.base_task import BaseTask
from movement.movement_controller import get_movement_controller
from movement.randomizer import human_sleep, micro_pause
from detection.mob_detector import mobs_present, mob_area_cleared, token_visible
from state.state_manager import get_state
from utils.logger import get_logger

log = get_logger(__name__)

_ATTACK_KEY = "z"  # user maps their attack key
_COLLECT_KEY = "f"
_CLEAR_TIMEOUT_SEC = 90


class MobRunTask(BaseTask):
    def __init__(self, fsm, profile: dict) -> None:
        super().__init__("mob_run")
        self._fsm = fsm
        self._profile = profile

    def run(self) -> None:
        sm = get_state()
        mc = get_movement_controller()
        route: list[str] = self._profile.get("mob_route", [])
        max_retries: int = 3

        if not route:
            log.warning("MobRunTask: no mob route configured, skipping")
            return

        sm.set(mob_run_count=sm.mob_run_count + 1)
        log.info("MobRunTask: starting route (%d locations)", len(route))

        for location in route:
            if self._check_stop():
                break

            retries = 0
            while retries <= max_retries:
                if self._check_stop():
                    break

                log.info("MobRunTask: navigating to '%s' (attempt %d)", location, retries + 1)
                mc.navigate_to(location, stop_event=self._stop_event, timeout_sec=60)
                human_sleep(800, 150)

                if self._defeat_mobs(mc):
                    self._collect_tokens()
                    break
                else:
                    retries += 1
                    log.warning("MobRunTask: stuck at '%s', retry %d/%d", location, retries, max_retries)
                    human_sleep(2000, 300)

            if retries > max_retries:
                log.error("MobRunTask: max retries reached at '%s', skipping", location)

        # Return to assigned field
        field = self._profile.get("target_field", "")
        if field and not self._check_stop():
            log.info("MobRunTask: returning to '%s'", field)
            mc.navigate_to(field, stop_event=self._stop_event, timeout_sec=90)

        log.info("MobRunTask complete")

    def _defeat_mobs(self, mc) -> bool:
        """Attack until area cleared or timeout. Returns True if cleared."""
        start = time.time()
        while time.time() - start < _CLEAR_TIMEOUT_SEC:
            if self._check_stop():
                return False

            if mob_area_cleared():
                log.info("MobRunTask: area cleared")
                return True

            if mobs_present():
                pyautogui.keyDown(_ATTACK_KEY)
                human_sleep(300, 80)
                pyautogui.keyUp(_ATTACK_KEY)
                micro_pause(0.15)
            else:
                # No mobs visible; might be cleared or we're in wrong spot
                human_sleep(500, 100)

            mc.hold_key("w", 0.2, self._stop_event)  # slight forward push

        return mob_area_cleared()

    def _collect_tokens(self) -> None:
        """Walk around briefly to pick up dropped tokens."""
        mc = get_movement_controller()
        start = time.time()
        while time.time() - start < 8.0:
            if self._check_stop():
                return
            if not token_visible():
                break
            pyautogui.press(_COLLECT_KEY)
            mc.hold_key("w", 0.3, self._stop_event)
            human_sleep(200, 50)
