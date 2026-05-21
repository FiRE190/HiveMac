"""
Abstract base for all macro tasks.  Every task has:
  - run()    — blocking; does the work
  - pause()  — suspends run loop
  - resume() — resumes run loop
  - stop()   — signals run() to exit cleanly
  - on_error(exc) — called on unhandled exceptions

Subclasses override run() and call _check_stop() / _check_pause() in their loops.
"""
import threading
import time
from abc import ABC, abstractmethod
from typing import Optional

from utils.logger import get_logger
from state.state_manager import get_state

log = get_logger(__name__)


class BaseTask(ABC):
    def __init__(self, name: str) -> None:
        self.name = name
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # not paused initially
        self._error: Optional[Exception] = None
        self._started_at: float = 0.0

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def run(self) -> None:
        """Blocking task implementation. Called from a background thread."""
        ...

    def start_threaded(self) -> threading.Thread:
        """Convenience: start this task in a daemon thread."""
        t = threading.Thread(target=self._run_wrapper, name=f"task-{self.name}", daemon=True)
        self._started_at = time.time()
        self._stop_event.clear()
        self._pause_event.set()
        t.start()
        log.info("Task '%s' started", self.name)
        return t

    def _run_wrapper(self) -> None:
        try:
            self.run()
        except Exception as exc:
            self._error = exc
            self.on_error(exc)

    def pause(self) -> None:
        self._pause_event.clear()
        log.debug("Task '%s' paused", self.name)

    def resume(self) -> None:
        self._pause_event.set()
        log.debug("Task '%s' resumed", self.name)

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.set()  # unblock any waiting pause
        log.info("Task '%s' stop requested", self.name)

    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def on_error(self, exc: Exception) -> None:
        sm = get_state()
        sm.set(error_count=sm.error_count + 1, last_error=str(exc))
        log.error("Task '%s' error: %s", self.name, exc, exc_info=True)

        from utils.screenshot_logger import log_error_screenshot
        log_error_screenshot(context=self.name)

    # ------------------------------------------------------------------ #
    # Helpers for subclasses                                               #
    # ------------------------------------------------------------------ #

    def _check_stop(self) -> bool:
        """Returns True if task should exit."""
        return self._stop_event.is_set()

    def _wait_resume(self) -> bool:
        """Block while paused. Returns False if stopped while waiting."""
        while not self._pause_event.wait(timeout=0.1):
            if self._stop_event.is_set():
                return False
        return not self._stop_event.is_set()

    def elapsed_sec(self) -> float:
        return time.time() - self._started_at if self._started_at else 0.0
