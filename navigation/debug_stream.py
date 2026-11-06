"""
Navigation debug stream — structured per-frame telemetry.

Writes JSON-lines to debug/nav_<timestamp>.jsonl so navigation decisions
are inspectable after the fact.  Must be zero-overhead when nothing is
consuming the file; writes are buffered and flushed only on close or
explicit flush().

Public API:
    stream = get_debug_stream()
    stream.nav_frame(key="w", elapsed=0.5, speed_px_s=82.3,
                     terrain="GROUND", stalled=False,
                     landmarks=[("sunflower_field", 0.61)])
    stream.event("arrival_detected", landmark="sunflower_field", conf=0.61)
    stream.event("stall_recovery", attempt=2, strategy="strafe_jump")
    stream.flush()

Each record has a monotonic "t" field (seconds since stream open).
On process exit the stream auto-closes.
"""
from __future__ import annotations

import atexit
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Tuple

_DEBUG_DIR = Path(__file__).parent.parent / "debug"


class DebugStream:
    """
    Thread-safe JSON-lines telemetry writer.

    One instance per navigation session (new file each time get_debug_stream()
    is called for the first time, or after reset()).
    """

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._lock = threading.Lock()
        self._t0 = time.monotonic()
        self._f = open(path, "w", encoding="utf-8", buffering=1)  # line-buffered
        atexit.register(self.close)
        self._write({"event": "session_start", "path": str(path)})

    # ------------------------------------------------------------------ #
    # Core write                                                           #
    # ------------------------------------------------------------------ #

    def _write(self, record: dict) -> None:
        record["t"] = round(time.monotonic() - self._t0, 3)
        with self._lock:
            try:
                self._f.write(json.dumps(record) + "\n")
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # High-level helpers                                                   #
    # ------------------------------------------------------------------ #

    def nav_frame(
        self,
        *,
        key: Optional[str] = None,
        elapsed: Optional[float] = None,
        speed_px_s: Optional[float] = None,
        terrain: Optional[str] = None,
        stalled: Optional[bool] = None,
        heading_deg: Optional[float] = None,
        heading_uncertainty: Optional[float] = None,
        landmarks: Optional[List[Tuple[str, float]]] = None,
        position_node: Optional[str] = None,
        position_conf: Optional[float] = None,
        **extra: Any,
    ) -> None:
        """
        Record a single navigation control loop tick.

        landmarks: list of (landmark_name, confidence) tuples
        """
        r: dict = {}
        if key is not None:
            r["key"] = key
        if elapsed is not None:
            r["elapsed"] = round(elapsed, 3)
        if speed_px_s is not None:
            r["speed"] = round(speed_px_s, 1)
        if terrain is not None:
            r["terrain"] = terrain
        if stalled is not None:
            r["stalled"] = stalled
        if heading_deg is not None:
            r["heading"] = round(heading_deg, 1)
        if heading_uncertainty is not None:
            r["heading_unc"] = round(heading_uncertainty, 1)
        if landmarks:
            r["landmarks"] = [(name, round(conf, 3)) for name, conf in landmarks]
        if position_node is not None:
            r["pos"] = position_node
        if position_conf is not None:
            r["pos_conf"] = round(position_conf, 3)
        r.update(extra)
        self._write(r)

    def event(self, name: str, **kwargs: Any) -> None:
        """Record a named navigation event with optional payload."""
        self._write({"event": name, **{k: v for k, v in kwargs.items()}})

    def flush(self) -> None:
        with self._lock:
            try:
                self._f.flush()
            except Exception:
                pass

    def close(self) -> None:
        with self._lock:
            try:
                self._f.close()
            except Exception:
                pass


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[DebugStream] = None
_inst_lock = threading.Lock()


def get_debug_stream() -> DebugStream:
    """
    Returns the session-level DebugStream, creating it on first call.
    Each call to reset_debug_stream() opens a new file.
    """
    global _instance
    with _inst_lock:
        if _instance is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = _DEBUG_DIR / f"nav_{ts}.jsonl"
            _instance = DebugStream(path)
    return _instance


def reset_debug_stream() -> DebugStream:
    """Open a new debug file (call at session start or after respawn)."""
    global _instance
    with _inst_lock:
        if _instance is not None:
            _instance.close()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _DEBUG_DIR / f"nav_{ts}.jsonl"
        _instance = DebugStream(path)
    return _instance
