"""
Finite state machine for the macro control flow.

Valid states:
  IDLE, FARMING, RETURNING_TO_HIVE, CONVERTING_POLLEN,
  WEALTH_CLOCK, MOB_RUN, DEATH_RECOVERY, PAUSED

Transitions are validated against an allow-list; illegal transitions raise ValueError.
"""
import threading
from typing import Callable
from utils.logger import get_logger
from state.state_manager import StateManager

log = get_logger(__name__)

# States
IDLE = "IDLE"
FARMING = "FARMING"
RETURNING_TO_HIVE = "RETURNING_TO_HIVE"
CONVERTING_POLLEN = "CONVERTING_POLLEN"
WEALTH_CLOCK = "WEALTH_CLOCK"
MOB_RUN = "MOB_RUN"
DEATH_RECOVERY = "DEATH_RECOVERY"
PAUSED = "PAUSED"

ALL_STATES = {
    IDLE, FARMING, RETURNING_TO_HIVE, CONVERTING_POLLEN,
    WEALTH_CLOCK, MOB_RUN, DEATH_RECOVERY, PAUSED,
}

# (from_state, to_state) pairs that are legal
_ALLOWED: set[tuple[str, str]] = {
    (IDLE,               FARMING),
    (FARMING,            RETURNING_TO_HIVE),
    (FARMING,            WEALTH_CLOCK),
    (FARMING,            MOB_RUN),
    (FARMING,            DEATH_RECOVERY),
    (FARMING,            IDLE),
    (RETURNING_TO_HIVE,  CONVERTING_POLLEN),
    (RETURNING_TO_HIVE,  IDLE),
    (CONVERTING_POLLEN,  FARMING),
    (CONVERTING_POLLEN,  IDLE),
    (WEALTH_CLOCK,       FARMING),
    (WEALTH_CLOCK,       IDLE),
    (MOB_RUN,            FARMING),
    (MOB_RUN,            IDLE),
    (DEATH_RECOVERY,     FARMING),
    (DEATH_RECOVERY,     IDLE),
    # Any → PAUSED and PAUSED → prior state
    (FARMING,            PAUSED),
    (RETURNING_TO_HIVE,  PAUSED),
    (CONVERTING_POLLEN,  PAUSED),
    (WEALTH_CLOCK,       PAUSED),
    (MOB_RUN,            PAUSED),
    (DEATH_RECOVERY,     PAUSED),
    (PAUSED,             FARMING),
    (PAUSED,             RETURNING_TO_HIVE),
    (PAUSED,             CONVERTING_POLLEN),
    (PAUSED,             WEALTH_CLOCK),
    (PAUSED,             MOB_RUN),
    (PAUSED,             DEATH_RECOVERY),
    (PAUSED,             IDLE),
    # Emergency stop from any state
    *{(s, IDLE) for s in ALL_STATES},
}


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
                log.warning("FSM: illegal transition %s → %s", from_state, to_state)
                return False

            log.info("FSM: %s → %s", from_state, to_state)
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
