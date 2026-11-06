import json
import urllib.error
import urllib.request

from remote.server import RemoteServer


class FakeController:
    def __init__(self):
        self.calls = []
        self.profile = {"name": "p", "fields": [{"name": "sunflower", "enabled": True}]}
        self.settings = {"walk_speed": 28, "hive_slot": 1}
        self.state = "IDLE"
    def status(self):
        return {"state": self.state, "backpack_pct": 12}
    def start(self):
        self.calls.append("start")
        self.state = "GATHERING"
    def pause(self):
        self.calls.append("pause")
        self.state = "PAUSED"
    def resume(self):
        self.calls.append("resume")
    def stop(self):
        self.calls.append("stop")
        self.state = "IDLE"
    def get_profile(self):
        return self.profile
    def set_profile(self, p):
        self.profile = p
    def get_settings(self):
        return self.settings
    def set_settings(self, s):
        self.settings.update(s)
    def log_tail(self, n):
        return ["a", "b"][:n]


def _req(url, method="GET", body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Token", token)
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, r.read().decode()


def test_remote_server_round_trip():
    ctl = FakeController()
    srv = RemoteServer(ctl, port=0, token="abc", bind="127.0.0.1")
    port = srv.start()
    base = f"http://127.0.0.1:{port}"
    try:
        # page needs the token
        try:
            _req(base + "/")
        except urllib.error.HTTPError as e:
            assert e.code == 401
        status, html = _req(base + "/?t=abc")
        assert status == 200 and "HiveMac" in html
        # api
        try:
            _req(base + "/api/status")
        except urllib.error.HTTPError as e:
            assert e.code == 401
        s, body = _req(base + "/api/status", token="abc")
        assert json.loads(body)["state"] == "IDLE"
        s, body = _req(base + "/api/start", "POST", {}, token="abc")
        assert json.loads(body)["status"]["state"] == "GATHERING"
        _req(base + "/api/pause", "POST", {}, token="abc")
        _req(base + "/api/resume", "POST", {}, token="abc")
        _req(base + "/api/stop", "POST", {}, token="abc")
        assert ctl.calls == ["start", "pause", "resume", "stop"]
        _req(base + "/api/settings", "POST", {"walk_speed": 31}, token="abc")
        assert ctl.settings["walk_speed"] == 31
        _req(base + "/api/profile", "POST", {"name": "p", "fields": []}, token="abc")
        assert ctl.profile["fields"] == []
        s, body = _req(base + "/api/log?n=1", token="abc")
        assert json.loads(body)["lines"] == ["a"]
        try:
            _req(base + "/api/nothing", token="abc")
        except urllib.error.HTTPError as e:
            assert e.code == 404
        assert any("t=abc" in u for u in srv.urls())
    finally:
        srv.stop()
