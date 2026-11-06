"""
FarmingService: the central coordinator that bridges the UI to all backend tasks.

Owns:
  - The active FarmingTask thread
  - The TaskScheduler (wealth clock + mob run timers)
  - The runtime timer thread
  - FSM state transitions
"""
import threading
import time
from typing import Optional

from state.fsm import FSM, IDLE, FARMING, WEALTH_CLOCK, MOB_RUN, PAUSED
from state.state_manager import get_state
from tasks.farming_task import FarmingTask
from tasks.hive_task import HiveTask
from tasks.wealth_clock_task import WealthClockTask
from tasks.mob_run_task import MobRunTask
from tasks.death_recovery_task import DeathRecoveryTask
from tasks.task_scheduler import TaskScheduler
from services.power_manager import PowerManager
from utils.logger import get_logger

log = get_logger(__name__)


class FarmingService:
    def __init__(self) -> None:
        self._sm = get_state()
        self._fsm = FSM(self._sm)
        self._scheduler = TaskScheduler()
        self._power_manager = PowerManager()
        self._farming_task: Optional[FarmingTask] = None
        self._farming_thread: Optional[threading.Thread] = None
        self._runtime_thread: Optional[threading.Thread] = None
        self._runtime_stop = threading.Event()
        self._active_profile: dict = {}
        self._interrupt_task = None          # WealthClockTask / MobRunTask while one runs
        self._scheduler_lock = threading.Lock()
        self._interrupt_lock = threading.Lock()

        self._setup_scheduler_callbacks()

    # ------------------------------------------------------------------ #
    # Public API (called from UI thread)                                   #
    # ------------------------------------------------------------------ #

    def start(self, profile: dict) -> None:
        if self._sm.current_state not in (IDLE,):
            log.warning("Cannot start: current state is %s", self._sm.current_state)
            return

        self._active_profile = profile
        self._sm.set(
            active_profile=profile,
            active_profile_name=profile.get("name", "unknown"),
            current_field=profile.get("target_field", ""),
            is_paused=False,
            farming_start_time=time.time(),
            error_count=0,
        )

        if not self._fsm.transition(FARMING):
            log.error("FSM refused IDLE → FARMING transition")
            return

        self._start_farming_task(profile)
        self._start_runtime_timer()

        if profile.get("reduce_brightness", False):
            self._power_manager.reduce_brightness(profile.get("brightness_level", 50))
        # Mob runs are off unless the profile enables them: they need templates that do not exist yet.
        if profile.get("wealth_clock_enabled", True) or profile.get("mob_run_enabled", False):
            self._start_scheduler(profile)

        log.info("FarmingService started with profile '%s'", profile.get("name"))

    def pause(self) -> None:
        if self._sm.current_state == FARMING:
            self._fsm.transition(PAUSED)
            self._sm.set(is_paused=True)
            if self._farming_task:
                self._farming_task.pause()
            log.info("FarmingService paused")

    def resume(self) -> None:
        if self._sm.current_state == PAUSED:
            prev = self._sm.previous_state
            self._fsm.transition(prev, force=True)
            self._sm.set(is_paused=False)
            if self._farming_task:
                self._farming_task.resume()
            log.info("FarmingService resumed")

    def stop(self) -> None:
        log.info("FarmingService stopping")
        self._scheduler.cancel_all()
        self._runtime_stop.set()

        if self._farming_task:
            self._farming_task.stop()           # also stops its hive / death child task
        if self._interrupt_task:
            self._interrupt_task.stop()
        self._release_input()

        self._sm.set(is_paused=False)
        self._fsm.transition(IDLE, force=True)
        self._power_manager.restore_brightness()
        log.info("FarmingService stopped")

    @property
    def fsm(self) -> FSM:
        return self._fsm

    @staticmethod
    def _release_input() -> None:
        """Let go of every key and mouse button, whatever a task was holding."""
        try:
            from execution.input_interface import get_input
            get_input().release_all()
        except Exception as exc:
            log.debug("release_all failed: %s", exc)
        try:
            import pyautogui
            pyautogui.mouseUp(button="left")
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _start_farming_task(self, profile: dict) -> None:
        self._farming_task = FarmingTask(self._fsm, profile)
        self._farming_task.set_hive_task_factory(
            lambda fsm, p: HiveTask(fsm, p)
        )
        self._farming_task.set_death_task_factory(
            lambda p: DeathRecoveryTask(p)
        )
        self._farming_thread = self._farming_task.start_threaded()

    def _start_runtime_timer(self) -> None:
        self._runtime_stop.clear()

        def _tick():
            start = time.time()
            while not self._runtime_stop.wait(timeout=1.0):
                self._sm.set(runtime_seconds=int(time.time() - start))

        self._runtime_thread = threading.Thread(
            target=_tick, name="runtime-timer", daemon=True
        )
        self._runtime_thread.start()

    def _start_scheduler(self, profile: dict) -> None:
        self._scheduler.start(
            wealth_interval_min=float(profile.get("wealth_clock_interval_min", 61)),
            mob_interval_min=float(profile.get("mob_run_interval_min", 64)),
        )

    def _setup_scheduler_callbacks(self) -> None:
        self._scheduler.set_wealth_clock_callback(self._on_wealth_clock_fire)
        self._scheduler.set_mob_run_callback(self._on_mob_run_fire)

    def _on_wealth_clock_fire(self) -> None:
        if self._sm.current_state not in (FARMING,):
            log.info("Wealth clock skipped (state=%s)", self._sm.current_state)
            return
        if not self._active_profile.get("wealth_clock_enabled", True):
            return

        with self._interrupt_lock:
            log.info("Wealth clock interrupt triggered")
            if self._farming_task:
                self._farming_task.pause()
            self._fsm.transition(WEALTH_CLOCK, force=True)

            task = WealthClockTask(self._fsm, self._active_profile)
            self._interrupt_task = task
            t = task.start_threaded()
            t.join(timeout=180)
            if t.is_alive():
                log.warning("Wealth clock task overran 180 s, stopping it")
                task.stop()
                t.join(timeout=10)
                self._release_input()
            self._interrupt_task = None

            self._fsm.transition(FARMING, force=True)
            if self._farming_task:
                self._farming_task.resume()

    def _on_mob_run_fire(self) -> None:
        if self._sm.current_state not in (FARMING,):
            log.info("Mob run skipped (state=%s)", self._sm.current_state)
            return
        if not self._active_profile.get("mob_run_enabled", False):
            return

        with self._interrupt_lock:
            log.info("Mob run interrupt triggered")
            if self._farming_task:
                self._farming_task.pause()
            self._fsm.transition(MOB_RUN, force=True)

            task = MobRunTask(self._fsm, self._active_profile)
            self._interrupt_task = task
            t = task.start_threaded()
            t.join(timeout=300)
            if t.is_alive():
                log.warning("Mob run task overran 300 s, stopping it")
                task.stop()
                t.join(timeout=10)
                self._release_input()
            self._interrupt_task = None

            self._fsm.transition(FARMING, force=True)
            if self._farming_task:
                self._farming_task.resume()
