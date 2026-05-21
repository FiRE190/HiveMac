"""
Singleton thread-safe shared state.  All backend threads write here;
the UI reads via subscribe() callbacks or direct attribute access.
"""
import threading
import time
from typing import Callable, Any


class StateManager:
    _instance: "StateManager | None" = None
    _cls_lock = threading.Lock()

    def __new__(cls) -> "StateManager":
        with cls._cls_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._lock = threading.RLock()
                inst._subscribers: list[Callable] = []

                # ---- public state fields ---- #
                inst.current_state: str = "IDLE"
                inst.previous_state: str = "IDLE"
                inst.current_field: str = "None"
                inst.backpack_pct: int = 0
                inst.runtime_seconds: int = 0
                inst.is_paused: bool = False
                inst.active_profile_name: str = "default"
                inst.active_profile: dict = {}
                inst.last_heartbeat: float = time.time()
                inst.debug_mode: bool = False
                inst.farming_start_time: float | None = None
                inst.error_count: int = 0
                inst.last_error: str = ""
                inst.mob_run_count: int = 0
                inst.wealth_clock_count: int = 0

                cls._instance = inst
        return cls._instance

    # ------------------------------------------------------------------ #

    def set(self, **kwargs: Any) -> None:
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self, k):
                    setattr(self, k, v)
                else:
                    raise AttributeError(f"StateManager has no field '{k}'")
            self.last_heartbeat = time.time()
        self._notify()

    def heartbeat(self) -> None:
        with self._lock:
            self.last_heartbeat = time.time()

    def subscribe(self, callback: Callable) -> None:
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable) -> None:
        with self._lock:
            self._subscribers = [c for c in self._subscribers if c is not callback]

    def _notify(self) -> None:
        subs = []
        with self._lock:
            subs = list(self._subscribers)
        for cb in subs:
            try:
                cb()
            except Exception:
                pass

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "current_state": self.current_state,
                "previous_state": self.previous_state,
                "current_field": self.current_field,
                "backpack_pct": self.backpack_pct,
                "runtime_seconds": self.runtime_seconds,
                "is_paused": self.is_paused,
                "active_profile_name": self.active_profile_name,
                "debug_mode": self.debug_mode,
                "error_count": self.error_count,
                "last_error": self.last_error,
                "mob_run_count": self.mob_run_count,
                "wealth_clock_count": self.wealth_clock_count,
                "last_heartbeat": self.last_heartbeat,
            }


def get_state() -> StateManager:
    return StateManager()
