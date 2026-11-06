"""
FarmingService: builds the Game from config and profile, runs the FarmLoop in a
thread, mirrors the loop's status into the shared state, and is the Controller
behind the remote page.
"""
from __future__ import annotations

import collections
import logging
import threading
import time
from typing import Optional

from calibration.layout import WindowBounds
from config.config_manager import get_config
from macro.game import FieldConfig, Game, GameSettings
from macro.loop import FarmLoop, LoopStats
from movement.walk import RealClock
from profiles.profile_manager import get_profile_manager
from state.fsm import ERROR, IDLE, PAUSED, RUNNING_STATES, STATUS_TO_STATE, FSM
from state.state_manager import get_state
from utils.logger import LOG_QUEUE, get_logger

log = get_logger(__name__)


class _TailHandler(logging.Handler):
    def __init__(self, n: int = 300) -> None:
        super().__init__(level=logging.INFO)
        self.lines: collections.deque[str] = collections.deque(maxlen=n)
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lines.append(self.format(record))
        except Exception:
            pass


class FarmingService:
    def __init__(self) -> None:
        self._sm = get_state()
        self._fsm = FSM(self._sm)
        self._thread: Optional[threading.Thread] = None
        self._game: Optional[Game] = None
        self._loop: Optional[FarmLoop] = None
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._runtime_stop = threading.Event()
        self._profile: dict = {}
        self._lock = threading.RLock()
        self._tail = _TailHandler()
        logging.getLogger().addHandler(self._tail)
        self._remote = None

    # ------------------------------------------------------------------ build
    def _window_bounds(self) -> Optional[WindowBounds]:
        from calibration.roblox_finder import get_roblox_bounds
        cfg = get_config()
        b = get_roblox_bounds()
        if b is None and cfg.get("screen.use_saved_window", False):
            b = cfg.get("screen.roblox_window")
        if not b or b.get("width", 0) < 100:
            return None
        return WindowBounds(int(b["left"]), int(b["top"]), int(b["width"]), int(b["height"]))

    def _window_size(self):
        w = self._window_bounds()
        return (w.left, w.top, w.width, w.height) if w else None

    def build_game(self, stop: threading.Event, pause: threading.Event) -> Game:
        from detection.screen_capture import get_screen_capture
        from detection.sensors import ScreenSensors
        from execution.input_interface import get_input

        cfg = get_config()
        settings = GameSettings.from_config(cfg.get_section("game"))
        sensors = ScreenSensors(get_screen_capture(), self._window_bounds, cfg.get_section("hud"))
        return Game(get_input(), sensors, settings, RealClock(), stop_event=stop, pause_event=pause,
                    status=self._on_status, window_size=self._window_size)

    @staticmethod
    def fields_from_profile(profile: dict) -> list[FieldConfig]:
        return [FieldConfig.from_dict(d) for d in profile.get("fields", [])]

    # ---------------------------------------------------------------- control
    def start(self, profile: Optional[dict] = None) -> None:
        with self._lock:
            if self._sm.current_state not in (IDLE, ERROR):
                log.warning("Start ignored, state is %s", self._sm.current_state)
                return
            if profile is not None:
                self._profile = profile
            if not self._profile:
                self._profile = get_profile_manager().load_last_used()
            fields = [f for f in self.fields_from_profile(self._profile) if f.enabled]
            if not fields:
                log.error("No enabled fields in profile '%s'", self._profile.get("name"))
                return
            self._stop = threading.Event()
            self._pause = threading.Event()
            try:
                self._game = self.build_game(self._stop, self._pause)
            except Exception as exc:
                log.error("Could not build the game: %s", exc, exc_info=True)
                return
            self._loop = FarmLoop(self._game, fields, on_stats=self._on_stats)
            self._sm.set(active_profile=self._profile, active_profile_name=self._profile.get("name", "default"),
                         current_field="", is_paused=False, farming_start_time=time.time(), error_count=0,
                         cycles=0, converts=0, deaths=0, resets=0, last_result="", detail="")
            self._fsm.transition(IDLE, force=True)
            self._thread = threading.Thread(target=self._run, name="farm-loop", daemon=True)
            self._thread.start()
            self._start_runtime_timer()
            if get_config().get("power.caffeinate", True):
                self._caffeinate(True)
            log.info("Started with profile '%s', fields %s", self._profile.get("name"), [f.name for f in fields])

    def _run(self) -> None:
        try:
            why = self._loop.run() if self._loop else "no_loop"
            log.info("Loop ended: %s", why)
            if why in ("reset_failed", "no_fields"):
                self._fsm.transition(ERROR, force=True)
                self._sm.set(detail=why)
                return
        except Exception as exc:
            log.error("Loop crashed: %s", exc, exc_info=True)
            self._sm.set(error_count=self._sm.error_count + 1, last_error=str(exc), detail=str(exc))
            self._fsm.transition(ERROR, force=True)
            return
        finally:
            try:
                from execution.input_interface import get_input
                get_input().release_all()
            except Exception:
                pass
            self._runtime_stop.set()
            self._caffeinate(False)
        self._fsm.transition(IDLE, force=True)

    def pause(self) -> None:
        if self._sm.current_state in RUNNING_STATES:
            self._pause.set()
            self._sm.set(is_paused=True)
            self._fsm.transition(PAUSED)
            log.info("Paused")

    def resume(self) -> None:
        if self._sm.current_state == PAUSED:
            prev = self._sm.previous_state if self._sm.previous_state in RUNNING_STATES else "RESETTING"
            self._pause.clear()
            self._sm.set(is_paused=False)
            self._fsm.transition(prev, force=True)
            log.info("Resumed")

    def stop(self) -> None:
        log.info("Stopping")
        self._stop.set()
        self._pause.clear()
        self._runtime_stop.set()
        if self._game:
            try:
                self._game.release_everything()
            except Exception:
                pass
        t = self._thread
        if t and t.is_alive() and threading.current_thread() is not t:
            t.join(timeout=5)
        self._sm.set(is_paused=False)
        self._fsm.transition(IDLE, force=True)
        self._caffeinate(False)

    @property
    def fsm(self) -> FSM:
        return self._fsm

    @property
    def running(self) -> bool:
        return self._sm.current_state not in (IDLE, ERROR)

    # -------------------------------------------------------------- callbacks
    def _on_status(self, state: str, detail: str) -> None:
        self._sm.heartbeat()
        target = STATUS_TO_STATE.get(state)
        if state == "warning":
            log.warning(detail)
            self._sm.set(detail=detail)
            return
        if target and self._sm.current_state != PAUSED:
            self._fsm.transition(target, force=True)
        if state == "traveling":
            self._sm.set(current_field=detail)
        if state == "gathering" and self._game:
            self._sm.set(backpack_pct=self._game.sensors.backpack_percent() if detail else self._sm.backpack_pct)
        self._sm.set(detail=detail)
        log.info("%s %s", state, detail)

    def _on_stats(self, stats: LoopStats) -> None:
        self._sm.set(cycles=stats.cycles, converts=stats.converts, deaths=stats.deaths,
                     resets=stats.resets, last_result=stats.last_result)

    def _start_runtime_timer(self) -> None:
        self._runtime_stop = threading.Event()

        def _tick():
            start = time.time()
            while not self._runtime_stop.wait(timeout=1.0):
                self._sm.set(runtime_seconds=int(time.time() - start))
                if self._game and self._sm.current_state in RUNNING_STATES:
                    try:
                        self._sm.set(backpack_pct=self._game.sensors.backpack_percent())
                    except Exception:
                        pass

        threading.Thread(target=_tick, name="runtime-timer", daemon=True).start()

    _caffeinate_proc = None

    def _caffeinate(self, on: bool) -> None:
        import subprocess
        try:
            if on and self._caffeinate_proc is None:
                self._caffeinate_proc = subprocess.Popen(["caffeinate", "-dis"])
            elif not on and self._caffeinate_proc is not None:
                self._caffeinate_proc.terminate()
                self._caffeinate_proc = None
        except Exception as exc:
            log.debug("caffeinate: %s", exc)

    # -------------------------------------------------------- remote Controller
    def status(self) -> dict:
        return self._sm.snapshot()

    def get_profile(self) -> dict:
        return dict(self._profile or get_profile_manager().load_last_used())

    def set_profile(self, profile: dict) -> None:
        if not isinstance(profile, dict) or "fields" not in profile:
            raise ValueError("profile needs a fields list")
        for f in profile["fields"]:
            FieldConfig.from_dict(f)   # validates
        self._profile = profile
        get_profile_manager().save(profile)
        self._sm.set(active_profile=profile, active_profile_name=profile.get("name", "default"))

    def get_settings(self) -> dict:
        cfg = get_config()
        return cfg.get_section("game")

    def set_settings(self, settings: dict) -> None:
        cfg = get_config()
        allowed = GameSettings().__dict__.keys()
        for k, v in settings.items():
            if k in allowed:
                cfg.set(f"game.{k}", v)
        cfg.save()
        GameSettings.from_config(cfg.get_section("game"))   # validates

    def log_tail(self, n: int = 60) -> list[str]:
        return list(self._tail.lines)[-max(1, min(n, 300)):]

    # ----------------------------------------------------------------- remote
    def start_remote(self) -> list[str]:
        from remote.server import RemoteServer
        cfg = get_config()
        if not cfg.get("remote.enabled", True):
            return []
        token = cfg.get("remote.token") or ""
        srv = RemoteServer(self, port=int(cfg.get("remote.port", 8765)), token=token or None)
        if not token:
            cfg.set("remote.token", srv.token)
            cfg.save()
        try:
            srv.start()
        except OSError as exc:
            log.warning("Remote server could not start: %s", exc)
            return []
        self._remote = srv
        urls = srv.urls()
        self._sm.set(remote_urls=urls)
        for u in urls:
            log.info("Remote control: %s", u)
        return urls

    def stop_remote(self) -> None:
        if self._remote:
            self._remote.stop()
            self._remote = None


_ = LOG_QUEUE  # the UI console reads this queue; imported here so the module graph is explicit
