"""
Remote control over the local network: a small HTTP server with a phone sized
page and a JSON API. No cloud, no extra packages. Reach it from any device on
the same Wi-Fi or over Tailscale at http://<this mac>:<port>/?t=<token>.

The server talks to a `Controller` (the FarmingService in production, a fake in
tests) and never imports the UI.
"""
from __future__ import annotations

import json
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Protocol
from urllib.parse import parse_qs, urlparse

from utils.logger import get_logger

log = get_logger(__name__)


class Controller(Protocol):
    def status(self) -> dict: ...
    def start(self) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def stop(self) -> None: ...
    def get_profile(self) -> dict: ...
    def set_profile(self, profile: dict) -> None: ...
    def get_settings(self) -> dict: ...
    def set_settings(self, settings: dict) -> None: ...
    def log_tail(self, n: int) -> list[str]: ...


def local_addresses() -> list[str]:
    """Best effort list of this machine's IPv4 addresses (LAN and Tailscale)."""
    addrs: list[str] = []
    # A UDP connect never sends anything; it just asks the kernel which local
    # address would be used for that destination. No DNS, no blocking.
    for probe in ("10.255.255.255", "192.168.255.255", "100.64.0.1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.2)
            s.connect((probe, 1))
            ip = s.getsockname()[0]
            s.close()
            if ip not in addrs and not ip.startswith("127."):
                addrs.append(ip)
        except Exception:
            pass
    return addrs


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HiveMac</title>
<style>
body{font-family:-apple-system,Helvetica,Arial,sans-serif;background:#111827;color:#e5e7eb;margin:0;padding:16px}
h1{font-size:20px;margin:0 0 12px}
.card{background:#1f2937;border-radius:12px;padding:14px;margin-bottom:12px}
.row{display:flex;gap:8px;flex-wrap:wrap}
button{flex:1;min-width:90px;padding:14px;border:0;border-radius:10px;font-size:16px;font-weight:600;color:#fff}
.start{background:#065f46}.pause{background:#78350f}.stop{background:#7f1d1d}.save{background:#1d4ed8}
.pill{display:inline-block;padding:4px 10px;border-radius:8px;background:#374151;font-weight:700}
label{display:block;font-size:13px;color:#9ca3af;margin-top:8px}
input,select{width:100%;box-sizing:border-box;padding:10px;border-radius:8px;border:1px solid #374151;background:#111827;color:#e5e7eb;font-size:15px}
pre{white-space:pre-wrap;font-size:12px;color:#9ca3af;max-height:220px;overflow:auto}
table{width:100%;border-collapse:collapse;font-size:13px}td{padding:4px 2px;border-bottom:1px solid #374151}
.small{font-size:12px;color:#9ca3af}
</style></head><body>
<h1>HiveMac <span id="state" class="pill">...</span></h1>
<div class="card">
 <div id="detail" class="small">loading</div>
 <table><tr><td>Field</td><td id="field"></td></tr><tr><td>Backpack</td><td id="bp"></td></tr>
 <tr><td>Runtime</td><td id="rt"></td></tr><tr><td>Cycles / converts / deaths</td><td id="counts"></td></tr></table>
 <div class="row" style="margin-top:10px">
  <button class="start" onclick="act('start')">Start</button>
  <button class="pause" id="pausebtn" onclick="act(pauseAction)">Pause</button>
  <button class="stop" onclick="act('stop')">Stop</button>
 </div>
</div>
<div class="card"><b>Settings</b>
 <label>Walk speed</label><input id="s_walk_speed" type="number" step="0.1">
 <label>Hive slot (1 to 6)</label><input id="s_hive_slot" type="number" min="1" max="6">
 <label>Sprinkler type</label><select id="s_sprinkler_type"><option>none</option><option>basic</option><option>silver</option><option>golden</option><option>diamond</option><option>supreme</option></select>
 <label>Travel</label><select id="s_travel"><option>walk</option><option>cannon</option></select>
 <div class="row" style="margin-top:10px"><button class="save" onclick="saveSettings()">Save settings</button></div>
</div>
<div class="card"><b>Fields</b><div id="fields"></div>
 <div class="row" style="margin-top:10px"><button class="save" onclick="saveProfile()">Save fields</button></div>
</div>
<div class="card"><b>Log</b><pre id="log"></pre></div>
<script>
const t=new URLSearchParams(location.search).get('t')||'';
const H={'Content-Type':'application/json','X-Token':t};
let pauseAction='pause';let profile=null;
async function api(p,body){const r=await fetch('/api/'+p+'?t='+encodeURIComponent(t),{method:body?'POST':'GET',headers:H,body:body?JSON.stringify(body):undefined});if(!r.ok){throw new Error(await r.text())}return r.json()}
async function act(a){try{await api(a,{})}catch(e){alert(e.message)}refresh()}
function fmt(s){s=Math.floor(s);return String(Math.floor(s/3600)).padStart(2,'0')+':'+String(Math.floor(s%3600/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0')}
async function refresh(){try{const s=await api('status');document.getElementById('state').textContent=s.state;document.getElementById('detail').textContent=s.detail||'';
document.getElementById('field').textContent=s.field||'';document.getElementById('bp').textContent=(s.backpack_pct||0)+'%';document.getElementById('rt').textContent=fmt(s.runtime_seconds||0);
document.getElementById('counts').textContent=(s.cycles||0)+' / '+(s.converts||0)+' / '+(s.deaths||0);
pauseAction=s.state==='PAUSED'?'resume':'pause';document.getElementById('pausebtn').textContent=s.state==='PAUSED'?'Resume':'Pause';
const l=await api('log');document.getElementById('log').textContent=l.lines.join('\\n');}catch(e){document.getElementById('detail').textContent='offline: '+e.message}}
async function loadForms(){const s=await api('settings');for(const k of ['walk_speed','hive_slot','sprinkler_type','travel']){const el=document.getElementById('s_'+k);if(el&&s[k]!==undefined)el.value=s[k]}
profile=await api('profile');const box=document.getElementById('fields');box.innerHTML='';(profile.fields||[]).forEach((f,i)=>{box.innerHTML+=`<div style="margin-top:8px;padding:8px;border:1px solid #374151;border-radius:8px"><label><input type="checkbox" id="f_en_${i}" ${f.enabled!==false?'checked':''} style="width:auto"> ${f.name}</label>
<label>Pattern</label><input id="f_pat_${i}" value="${f.pattern||''}"><label>Size / width</label><div class="row"><input id="f_size_${i}" value="${f.size||'m'}"><input id="f_width_${i}" type="number" value="${f.width||1}"></div>
<label>Minutes / backpack %</label><div class="row"><input id="f_min_${i}" type="number" step="0.5" value="${f.minutes||10}"><input id="f_bp_${i}" type="number" value="${f.backpack_percent||95}"></div></div>`})}
async function saveSettings(){const s={};for(const k of ['walk_speed','hive_slot','sprinkler_type','travel']){s[k]=document.getElementById('s_'+k).value}try{await api('settings',s);alert('saved')}catch(e){alert(e.message)}}
async function saveProfile(){(profile.fields||[]).forEach((f,i)=>{f.enabled=document.getElementById('f_en_'+i).checked;f.pattern=document.getElementById('f_pat_'+i).value;f.size=document.getElementById('f_size_'+i).value;f.width=+document.getElementById('f_width_'+i).value;f.minutes=+document.getElementById('f_min_'+i).value;f.backpack_percent=+document.getElementById('f_bp_'+i).value});try{await api('profile',profile);alert('saved')}catch(e){alert(e.message)}}
loadForms();refresh();setInterval(refresh,2000);
</script></body></html>"""


class RemoteServer:
    def __init__(self, controller: Controller, port: int = 8765, token: Optional[str] = None,
                 bind: str = "0.0.0.0") -> None:
        self.controller = controller
        self.token = token or secrets.token_urlsafe(8)
        self.port = port
        self._bind = bind
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    # -- lifecycle ------------------------------------------------------------
    def start(self) -> int:
        server = self
        controller = self.controller

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):  # quiet
                log.debug("remote: " + fmt, *args)

            def _authed(self) -> bool:
                q = parse_qs(urlparse(self.path).query)
                tok = self.headers.get("X-Token") or (q.get("t") or [""])[0]
                return secrets.compare_digest(tok, server.token)

            def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype + "; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code: int, obj) -> None:
                self._send(code, json.dumps(obj).encode("utf-8"))

            def do_GET(self):
                path = urlparse(self.path).path
                if path == "/":
                    if not self._authed():
                        return self._send(401, b"<h3>Missing or wrong token. Open the link shown in the HiveMac window.</h3>", "text/html")
                    return self._send(200, PAGE.encode("utf-8"), "text/html")
                if not self._authed():
                    return self._json(401, {"error": "unauthorized"})
                if path == "/api/status":
                    return self._json(200, controller.status())
                if path == "/api/profile":
                    return self._json(200, controller.get_profile())
                if path == "/api/settings":
                    return self._json(200, controller.get_settings())
                if path == "/api/log":
                    q = parse_qs(urlparse(self.path).query)
                    n = int((q.get("n") or ["60"])[0])
                    return self._json(200, {"lines": controller.log_tail(n)})
                return self._json(404, {"error": "not found"})

            def do_POST(self):
                if not self._authed():
                    return self._json(401, {"error": "unauthorized"})
                path = urlparse(self.path).path
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                try:
                    body = json.loads(raw.decode("utf-8")) if raw else {}
                except ValueError:
                    return self._json(400, {"error": "bad json"})
                try:
                    if path == "/api/start":
                        controller.start()
                    elif path == "/api/pause":
                        controller.pause()
                    elif path == "/api/resume":
                        controller.resume()
                    elif path == "/api/stop":
                        controller.stop()
                    elif path == "/api/profile":
                        controller.set_profile(body)
                    elif path == "/api/settings":
                        controller.set_settings(body)
                    else:
                        return self._json(404, {"error": "not found"})
                except Exception as exc:
                    log.warning("remote action %s failed: %s", path, exc)
                    return self._json(500, {"error": str(exc)})
                return self._json(200, {"ok": True, "status": controller.status()})

        self._httpd = ThreadingHTTPServer((self._bind, self.port), Handler)
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="remote-http", daemon=True)
        self._thread.start()
        log.info("Remote control listening on port %d", self.port)
        return self.port

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    def urls(self) -> list[str]:
        return [f"http://{ip}:{self.port}/?t={self.token}" for ip in local_addresses()] or \
               [f"http://localhost:{self.port}/?t={self.token}"]
