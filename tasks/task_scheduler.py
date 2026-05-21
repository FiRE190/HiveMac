"""
Threaded scheduler for timed interruptions (Wealth Clock, Mob Run).
Uses self-rescheduling threading.Timer chains.

The scheduler fires a callback when the interval elapses.  The FarmingService
listens and handles the actual task switching.
"""
import threading
import time
from typing import Callable, Optional

from utils.logger import get_logger

log = get_logger(__name__)


class _RepeatingTimer:
    """Fires callback every interval_sec indefinitely until cancelled."""

    def __init__(self, interval_sec: float, callback: Callable, name: str) -> None:
        self._interval = interval_sec
        self._callback = callback
        self._name = name
        self._timer: Optional[threading.Timer] = None
        self._running = False
        self._fire_count = 0
        self._start_time: float = 0.0

    def start(self) -> None:
        self._running = True
        self._start_time = time.time()
        self._schedule()
        log.info("Scheduler '%s': will fire in %.0f min", self._name, self._interval / 60)

    def _schedule(self) -> None:
        if self._running:
            self._timer = threading.Timer(self._interval, self._fire)
            self._timer.daemon = True
            self._timer.name = f"timer-{self._name}"
            self._timer.start()

    def _fire(self) -> None:
        if not self._running:
            return
        self._fire_count += 1
        log.info("Scheduler '%s' fired (count=%d)", self._name, self._fire_count)
        try:
            self._callback()
        except Exception as e:
            log.error("Scheduler '%s' callback error: %s", self._name, e)
        self._schedule()

    def cancel(self) -> None:
        self._running = False
        if self._timer:
            self._timer.cancel()
        log.info("Scheduler '%s' cancelled", self._name)

    def reset(self) -> None:
        self.cancel()
        self.start()

    @property
    def fire_count(self) -> int:
        return self._fire_count


class TaskScheduler:
    def __init__(self) -> None:
        self._wealth_timer: Optional[_RepeatingTimer] = None
        self._mob_timer: Optional[_RepeatingTimer] = None
        self._wealth_callback: Optional[Callable] = None
        self._mob_callback: Optional[Callable] = None

    def set_wealth_clock_callback(self, cb: Callable) -> None:
        self._wealth_callback = cb

    def set_mob_run_callback(self, cb: Callable) -> None:
        self._mob_callback = cb

    def start(self, wealth_interval_min: float = 61, mob_interval_min: float = 64) -> None:
        if self._wealth_callback:
            self._wealth_timer = _RepeatingTimer(
                wealth_interval_min * 60, self._wealth_callback, "wealth_clock"
            )
            self._wealth_timer.start()

        if self._mob_callback:
            self._mob_timer = _RepeatingTimer(
                mob_interval_min * 60, self._mob_callback, "mob_run"
            )
            self._mob_timer.start()

    def cancel_all(self) -> None:
        if self._wealth_timer:
            self._wealth_timer.cancel()
        if self._mob_timer:
            self._mob_timer.cancel()

    def reset_wealth_clock(self) -> None:
        if self._wealth_timer:
            self._wealth_timer.reset()

    def reset_mob_run(self) -> None:
        if self._mob_timer:
            self._mob_timer.reset()
