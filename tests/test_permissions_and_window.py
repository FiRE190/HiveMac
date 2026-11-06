from calibration.roblox_finder import content_rect, pick_window
from setup import permissions


def _win(owner, x, y, w, h, layer=0):
    return {"kCGWindowOwnerName": owner, "kCGWindowLayer": layer,
            "kCGWindowBounds": {"X": x, "Y": y, "Width": w, "Height": h}}


def test_pick_window_chooses_the_largest_roblox_window():
    infos = [_win("Finder", 0, 0, 3000, 2000), _win("Roblox", 10, 20, 400, 300), _win("RobloxPlayer", 100, 50, 1600, 900),
             _win("Roblox", 0, 0, 3000, 40, layer=25), _win("Roblox", 5, 5, 50, 50)]
    assert pick_window(infos) == {"left": 100, "top": 50, "width": 1600, "height": 900}
    assert pick_window([_win("Finder", 0, 0, 800, 600)]) is None
    assert pick_window([]) is None
    assert pick_window([_win("Terminal", 1, 2, 800, 600)], owner_hint="terminal")["width"] == 800


def test_content_rect_windowed_removes_title_bar_and_fullscreen_does_not():
    w = {"left": 100, "top": 50, "width": 1600, "height": 900}
    assert content_rect(w, "windowed", 28) == {"left": 100, "top": 78, "width": 1600, "height": 872}
    assert content_rect(w, "fullscreen", 28) == w
    assert content_rect(w, "windowed", 9999)["height"] == 900 - 225      # capped at a quarter of the height
    assert content_rect(w, "windowed", -5) == w


class FakeBackend:
    def __init__(self, screen=True, post=True, listen=True, ax=True):
        self.s, self.p, self.l, self.a = screen, post, listen, ax
        self.requested = []
    def screen_capture(self):
        return self.s
    def post_events(self):
        return self.p
    def listen_events(self):
        return self.l
    def accessibility(self):
        return self.a
    def request_screen_capture(self):
        self.requested.append("screen")
    def request_post_events(self):
        self.requested.append("post")
    def request_listen_events(self):
        self.requested.append("listen")


def test_all_granted():
    r = permissions.check(FakeBackend())
    assert r.can_run and r.hotkey_ok and r.problems() == []


def test_missing_accessibility_blocks_running_and_explains():
    r = permissions.check(FakeBackend(post=False, ax=False))
    assert not r.can_run
    assert any("Accessibility" in p for p in r.problems())
    assert any("reopen your terminal" in p for p in r.problems())


def test_missing_input_monitoring_only_loses_the_hotkey():
    r = permissions.check(FakeBackend(listen=False))
    assert r.can_run and r.hotkey_ok is False
    assert any("F9" in p for p in r.problems())


def test_missing_screen_recording_blocks():
    r = permissions.check(FakeBackend(screen=False))
    assert not r.can_run and any("Screen Recording" in p for p in r.problems())


def test_request_all_only_asks_for_what_is_missing():
    b = FakeBackend(screen=False, post=True, ax=False, listen=False)
    permissions.request_all(b)
    assert sorted(b.requested) == ["listen", "post", "screen"]
    b2 = FakeBackend()
    permissions.request_all(b2)
    assert b2.requested == []
