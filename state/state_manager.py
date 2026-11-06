"""
Singleton thread safe shared state. Backend threads write here; the UI and the
remote page read snapshots.
"""
import threading
import time
from typing import Any, Callable


class StateManager:
    _instance: "StateManager | None" = None
    _cls_lock = threading.Lock()

    def __new__(cls) -> "StateManager":
        with cls._cls_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._lock = threading.RLock()
                inst._subscribers: list[Callable] = []
                inst.current_state: str = "IDLE"
                inst.previous_state: str = "IDLE"
                inst.detail: str = ""
                inst.current_field: str = ""
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
                inst.cycles: int = 0
                inst.converts: int = 0
                inst.deaths: int = 0
                inst.resets: int = 0
                inst.last_result: str = ""
                inst.remote_urls: list[str] = []
                cls._instance = inst
        return cls._instance

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
                "state": self.current_state,
                "previous_state": self.previous_state,
                "detail": self.detail,
                "field": self.current_field,
                "backpack_pct": self.backpack_pct,
                "runtime_seconds": self.runtime_seconds,
                "is_paused": self.is_paused,
                "profile": self.active_profile_name,
                "debug_mode": self.debug_mode,
                "error_count": self.error_count,
                "last_error": self.last_error,
                "cycles": self.cycles,
                "converts": self.converts,
                "deaths": self.deaths,
                "resets": self.resets,
                "last_result": self.last_result,
                "remote_urls": list(self.remote_urls),
                "last_heartbeat": self.last_heartbeat,
            }


def get_state() -> StateManager:
    return StateManager()
