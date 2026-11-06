"""
The macro's control states. The loop reports where it is; the UI and the remote
page show it. PAUSED can be entered from any running state and returns to the
previous one; IDLE can be reached from anywhere (stop).
"""
import threading
from typing import Callable

from state.state_manager import StateManager
from utils.logger import get_logger

log = get_logger(__name__)

IDLE = "IDLE"
RESETTING = "RESETTING"
CONVERTING = "CONVERTING"
TRAVELING = "TRAVELING"
GATHERING = "GATHERING"
PAUSED = "PAUSED"
ERROR = "ERROR"

ALL_STATES = {IDLE, RESETTING, CONVERTING, TRAVELING, GATHERING, PAUSED, ERROR}
RUNNING_STATES = {RESETTING, CONVERTING, TRAVELING, GATHERING}

_ALLOWED: set[tuple[str, str]] = {
    (IDLE, RESETTING),
    (RESETTING, CONVERTING), (RESETTING, TRAVELING), (RESETTING, RESETTING),
    (CONVERTING, TRAVELING), (CONVERTING, RESETTING),
    (TRAVELING, GATHERING), (TRAVELING, RESETTING),
    (GATHERING, RESETTING), (GATHERING, TRAVELING), (GATHERING, CONVERTING),
    *{(s, PAUSED) for s in RUNNING_STATES},
    *{(PAUSED, s) for s in RUNNING_STATES},
    *{(s, ERROR) for s in ALL_STATES},
    *{(s, IDLE) for s in ALL_STATES},
}

STATUS_TO_STATE = {"resetting": RESETTING, "converting": CONVERTING, "traveling": TRAVELING,
                   "gathering": GATHERING, "error": ERROR}


class FSM:
    def __init__(self, state_manager: StateManager) -> None:
        self._sm = state_manager
        self._lock = threading.RLock()
        self._enter_callbacks: dict[str, list[Callable]] = {s: [] for s in ALL_STATES}
        self._exit_callbacks: dict[str, list[Callable]] = {s: [] for s in ALL_STATES}

    @property
    def state(self) -> str:
        return self._sm.current_state

    def can_transition(self, to_state: str) -> bool:
        return (self._sm.current_state, to_state) in _ALLOWED

    def transition(self, to_state: str, force: bool = False) -> bool:
        with self._lock:
            from_state = self._sm.current_state
            if from_state == to_state:
                return True
            if not force and not self.can_transition(to_state):
                log.warning("FSM: illegal transition %s to %s", from_state, to_state)
                return False
            log.debug("FSM: %s to %s", from_state, to_state)
            for cb in self._exit_callbacks.get(from_state, []):
                try:
                    cb(from_state, to_state)
                except Exception as e:
                    log.error("FSM exit callback error: %s", e)
            self._sm.set(previous_state=from_state, current_state=to_state)
            for cb in self._enter_callbacks.get(to_state, []):
                try:
                    cb(from_state, to_state)
                except Exception as e:
                    log.error("FSM enter callback error: %s", e)
            return True

    def on_enter(self, state: str, callback: Callable) -> None:
        self._enter_callbacks.setdefault(state, []).append(callback)

    def on_exit(self, state: str, callback: Callable) -> None:
        self._exit_callbacks.setdefault(state, []).append(callback)
