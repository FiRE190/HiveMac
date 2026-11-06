"""
macOS permissions, asked the direct way instead of guessing.

What each one gates for HiveMac:
  Screen Recording   reading pixels (without it captures come back wrong or black)
  Accessibility /    posting key and mouse events (without it every key press is
  Post Event         silently dropped by macOS)
  Input Monitoring / the F9 stop hotkey (a global key listener)
  Listen Event

macOS grants these to the app that launched the process (Terminal, iTerm, Cursor,
the Python app...), not to Python itself. Launch HiveMac from the terminal you
granted. Changes only take effect after that terminal is restarted.

The backend is injectable so the explanation logic is tested without macOS.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


class Backend(Protocol):
    def screen_capture(self) -> bool: ...
    def post_events(self) -> bool: ...
    def listen_events(self) -> bool: ...
    def accessibility(self) -> bool: ...
    def request_screen_capture(self) -> None: ...
    def request_post_events(self) -> None: ...
    def request_listen_events(self) -> None: ...


class QuartzBackend:
    def __init__(self) -> None:
        import ApplicationServices
        import Quartz
        self._q = Quartz
        self._ax = ApplicationServices

    def screen_capture(self) -> bool:
        return bool(self._q.CGPreflightScreenCaptureAccess())

    def post_events(self) -> bool:
        return bool(self._q.CGPreflightPostEventAccess())

    def listen_events(self) -> bool:
        return bool(self._q.CGPreflightListenEventAccess())

    def accessibility(self) -> bool:
        return bool(self._ax.AXIsProcessTrusted())

    def request_screen_capture(self) -> None:
        self._q.CGRequestScreenCaptureAccess()

    def request_post_events(self) -> None:
        self._q.CGRequestPostEventAccess()
        try:
            self._ax.AXIsProcessTrustedWithOptions({self._ax.kAXTrustedCheckOptionPrompt: True})
        except Exception:
            pass

    def request_listen_events(self) -> None:
        self._q.CGRequestListenEventAccess()


@dataclass
class PermissionReport:
    screen_capture: Optional[bool]
    post_events: Optional[bool]
    listen_events: Optional[bool]
    accessibility: Optional[bool]

    @property
    def can_run(self) -> bool:
        """Needed to farm at all: read pixels and press keys."""
        return self.screen_capture is not False and self.keys_ok is not False

    @property
    def keys_ok(self) -> Optional[bool]:
        vals = [v for v in (self.post_events, self.accessibility) if v is not None]
        return None if not vals else all(vals)

    @property
    def hotkey_ok(self) -> Optional[bool]:
        return self.listen_events

    def problems(self) -> list[str]:
        out = []
        if self.screen_capture is False:
            out.append("Screen Recording is off: the macro cannot read the game. Turn it on for your terminal.")
        if self.keys_ok is False:
            out.append("Accessibility is off: macOS silently drops every key press. Turn it on for your terminal.")
        if self.hotkey_ok is False:
            out.append("Input Monitoring is off: the F9 stop key will not work. Use the Stop button or the phone page, "
                       "or turn Input Monitoring on for your terminal.")
        if out:
            out.append("After changing a permission, quit and reopen your terminal, then launch HiveMac again.")
        return out


_backend: Optional[Backend] = None


def _get_backend() -> Optional[Backend]:
    global _backend
    if _backend is None:
        try:
            _backend = QuartzBackend()
        except Exception:
            return None
    return _backend


def check(backend: Optional[Backend] = None) -> PermissionReport:
    b = backend or _get_backend()
    if b is None:
        return PermissionReport(None, None, None, None)
    return PermissionReport(b.screen_capture(), b.post_events(), b.listen_events(), b.accessibility())


def request_all(backend: Optional[Backend] = None) -> None:
    """Triggers the macOS prompts for anything missing. Safe to call repeatedly."""
    b = backend or _get_backend()
    if b is None:
        return
    rep = check(b)
    if rep.screen_capture is False:
        b.request_screen_capture()
    if rep.keys_ok is False:
        b.request_post_events()
    if rep.listen_events is False:
        b.request_listen_events()
