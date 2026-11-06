"""
Death recovery: wait for respawn, walk to the backup field, farm it for a while, then
return to the original field. Navigation uses the nav stack (RouteManager), the same path
as the hive trip. The player respawns on the spawn platform, which is a nav map node.
"""
import time

import pyautogui

from tasks.base_task import BaseTask
from movement.adaptive_controller import AdaptiveController
from movement.randomizer import human_sleep
from navigation.node_names import field_to_node
from navigation.route_manager import get_route_manager
from config.config_manager import get_config
from state.state_manager import get_state
from utils.logger import get_logger

log = get_logger(__name__)

_RESPAWN_WAIT_MS = 6000


class DeathRecoveryTask(BaseTask):
    def __init__(self, profile: dict) -> None:
        super().__init__("death_recovery")
        self._profile = profile

    def run(self) -> None:
        cfg = get_config()
        sm = get_state()
        rm = get_route_manager()

        original = field_to_node(self._profile.get("target_field", ""))
        backup = field_to_node(self._profile.get("backup_field", "Dandelion Field")) or "dandelion_field"
        recovery_min = float(cfg.get("death_recovery.backup_field_farming_min", 30))

        log.info("DeathRecoveryTask: farming '%s' for %.0f min, then back to '%s'",
                 backup, recovery_min, original)

        # Wait for the respawn, then tell the navigator we are on the spawn platform.
        human_sleep(_RESPAWN_WAIT_MS, 500)
        if self._check_stop():
            return
        from navigation.navigator import get_navigator
        get_navigator().snap_spawn()

        result = rm.execute(backup, self._stop_event)
        if result.outcome.name == "FAILED":
            log.warning("DeathRecoveryTask: could not reach '%s', farming where we stand", backup)
        sm.set(current_field=backup)

        # Farm the backup field with the same adaptive loop as normal farming.
        ac = AdaptiveController()
        pattern_name = self._profile.get("movement_pattern", "circular")
        hold_ms = cfg.get("timing.click_hold_ms", 120)
        start = time.time()
        for key, weight in ac.pattern_cycle(pattern_name):
            if self._check_stop() or not self._wait_resume():
                break
            if time.time() - start >= recovery_min * 60:
                break
            sm.heartbeat()
            ac.step(key, weight, self._stop_event)
            pyautogui.mouseDown(button="left")
            human_sleep(hold_ms, 20)
            pyautogui.mouseUp(button="left")
            human_sleep(80, 20)

        if original and not self._check_stop():
            log.info("DeathRecoveryTask: returning to '%s'", original)
            rm.execute(original, self._stop_event)
            sm.set(current_field=original)

        log.info("DeathRecoveryTask complete")
