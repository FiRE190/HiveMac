import Foundation
import Network
import Darwin

/// A tiny HTTP server for the phone: one page, status, log, and Start / Pause / Resume / Stop.
/// Same Wi-Fi or Tailscale only, and every request needs the token in the link.
/// It exists only while switched on, so it costs nothing otherwise.
final class RemoteServer {
    let port: UInt16
    let token: String
    var status: () -> [String: Any] = { [:] }
    var logLines: (Int) -> [String] = { _ in [] }
    var action: (String) -> Void = { _ in }

    private var listener: NWListener?
    private let queue = DispatchQueue(label: "hivemac.remote", qos: .utility)

    init(port: UInt16 = 8765, token: String) { self.port = port; self.token = token }

    func start() -> Bool {
        guard listener == nil, let p = NWEndpoint.Port(rawValue: port),
              let l = try? NWListener(using: .tcp, on: p) else { return false }
        l.newConnectionHandler = { [weak self] c in self?.handle(c) }
        l.start(queue: queue)
        listener = l
        return true
    }

    func stop() { listener?.cancel(); listener = nil }

    static func localAddresses() -> [String] {
        var out: [String] = []
        var ifap: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifap) == 0, let first = ifap else { return out }
        defer { freeifaddrs(ifap) }
        for p in sequence(first: first, next: { $0.pointee.ifa_next }) {
            let i = p.pointee
            guard let sa = i.ifa_addr, sa.pointee.sa_family == UInt8(AF_INET), (i.ifa_flags & UInt32(IFF_LOOPBACK)) == 0 else { continue }
            var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
            getnameinfo(sa, socklen_t(sa.pointee.sa_len), &host, socklen_t(host.count), nil, 0, NI_NUMERICHOST)
            let ip = String(cString: host)
            if !ip.hasPrefix("169.254") && !out.contains(ip) { out.append(ip) }
        }
        return out
    }

    // MARK: HTTP
    private func handle(_ c: NWConnection) {
        c.start(queue: queue)
        c.receive(minimumIncompleteLength: 1, maximumLength: 8192) { [weak self] data, _, _, _ in
            guard let self, let data, let text = String(data: data, encoding: .utf8) else { c.cancel(); return }
            let (code, type, body) = self.route(text)
            let head = "HTTP/1.1 \(code)\r\nContent-Type: \(type); charset=utf-8\r\nContent-Length: \(body.count)\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n"
            c.send(content: Data(head.utf8) + body, completion: .contentProcessed { _ in c.cancel() })
        }
    }

    private func route(_ request: String) -> (String, String, Data) {
        let parts = (request.split(separator: "\r\n").first ?? "").split(separator: " ")
        guard parts.count >= 2 else { return ("400 Bad Request", "text/plain", Data("bad request".utf8)) }
        let method = String(parts[0])
        let comps = URLComponents(string: String(parts[1]))
        let path = comps?.path ?? "/"
        let given = comps?.queryItems?.first { $0.name == "t" }?.value ?? ""
        let tokenOK = given.utf8.count == token.utf8.count && zip(given.utf8, token.utf8).reduce(0) { $0 | ($1.0 ^ $1.1) } == 0
        guard tokenOK else { return ("401 Unauthorized", "text/html", Data("<h3>Missing or wrong token. Use the link from HiveMac settings.</h3>".utf8)) }
        if path == "/" { return ("200 OK", "text/html", Data(Self.page.utf8)) }
        if method == "GET", path == "/api/status" { return json(DispatchQueue.main.sync { status() }) }
        if method == "GET", path == "/api/log" { return json(["lines": DispatchQueue.main.sync { logLines(60) }]) }
        if method == "POST", ["start", "pause", "resume", "stop"].contains(String(path.dropFirst(5))), path.hasPrefix("/api/") {
            let a = String(path.dropFirst(5))
            DispatchQueue.main.async { self.action(a) }
            return json(["ok": true])
        }
        return ("404 Not Found", "application/json", Data("{\"error\":\"not found\"}".utf8))
    }

    private func json(_ obj: Any) -> (String, String, Data) {
        ("200 OK", "application/json", (try? JSONSerialization.data(withJSONObject: obj)) ?? Data("{}".utf8))
    }

    static let page = """
    <!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HiveMac</title>
    <style>
    body{font-family:-apple-system,Helvetica,sans-serif;background:#1a1815;color:#efe9dc;margin:0;padding:16px}
    h1{font-size:20px;margin:0 0 12px}.card{background:#2c2823;border-radius:12px;padding:14px;margin-bottom:12px}
    .row{display:flex;gap:8px}button{flex:1;padding:14px;border:0;border-radius:10px;font-size:16px;font-weight:600;color:#efe9dc;background:#3a352e}
    .go{background:#f2b134;color:#1a1300}.stop{color:#e5604d}.k{color:#b3aa99;font-size:13px}
    pre{white-space:pre-wrap;font-size:12px;color:#b3aa99;max-height:260px;overflow:auto;margin:0}
    </style></head><body><h1>HiveMac <span id="s" class="k"></span></h1>
    <div class="card"><div id="d" class="k"></div><p>Backpack <b id="b"></b> &nbsp; Field <b id="f"></b><br>Cycles <b id="c"></b> &nbsp; Converts <b id="v"></b> &nbsp; Deaths <b id="x"></b></p>
    <div class="row"><button class="go" onclick="a('start')">Start</button><button id="p" onclick="a(P)">Pause</button><button class="stop" onclick="a('stop')">Stop</button></div></div>
    <div class="card"><pre id="l"></pre></div>
    <script>
    const t=new URLSearchParams(location.search).get('t')||'';let P='pause';
    async function api(p,m){const r=await fetch('/api/'+p+'?t='+encodeURIComponent(t),{method:m||'GET'});if(!r.ok)throw 0;return r.json()}
    async function a(x){try{await api(x,'POST')}catch(e){}setTimeout(r,300)}
    async function r(){try{const s=await api('status');s_.textContent=s.state;d.textContent=s.detail||'';b.textContent=(s.backpack==null?'n/a':s.backpack+'%');f.textContent=s.field||'-';
    c.textContent=s.cycles;v.textContent=s.converts;x.textContent=s.deaths;P=s.paused?'resume':'pause';p.textContent=s.paused?'Resume':'Pause';
    l.textContent=(await api('log')).lines.join('\\n')}catch(e){d.textContent='offline'}}
    const s_=document.getElementById('s'),d=document.getElementById('d'),b=document.getElementById('b'),f=document.getElementById('f'),c=document.getElementById('c'),v=document.getElementById('v'),x=document.getElementById('x'),p=document.getElementById('p'),l=document.getElementById('l');
    r();setInterval(r,2000)
    </script></body></html>
    """
}
