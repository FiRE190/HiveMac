import SwiftUI
import AppKit
import HiveMacCore
import HiveMacPlatform

extension AppModel {
    // MARK: Phone remote
    func setRemote(_ on: Bool) {
        remote?.stop(); remote = nil; remoteURL = ""; remoteMessage = nil
        guard on else { remoteOn = false; set("remote.enabled", false); return }
        var token = store.string("remote.token", "")
        if token.isEmpty { token = String((0..<10).map { _ in "abcdefghjkmnpqrstuvwxyz23456789".randomElement()! }); store.set("remote.token", token); try? store.save() }
        let server = RemoteServer(token: token)
        server.status = { [weak self] in
            guard let self else { return [:] }
            return ["state": self.state.label, "detail": self.detail, "field": self.currentField, "backpack": self.backpack as Any? ?? NSNull(),
                    "cycles": self.stats.cycles, "converts": self.stats.converts, "deaths": self.stats.deaths, "paused": self.paused, "running": self.running]
        }
        server.logLines = { [weak self] n in Array((self?.log ?? []).suffix(n)) }
        server.action = { [weak self] a in
            switch a { case "start": self?.start(); case "pause": self?.pause(); case "resume": self?.resume(); default: self?.stop() }
        }
        guard server.start() else { remoteOn = false; remoteMessage = "Port 8765 is busy. Close the other HiveMac and try again."; return }
        remote = server; remoteOn = true; set("remote.enabled", true)
        let ip = RemoteServer.localAddresses().first ?? "localhost"
        remoteURL = "http://\(ip):8765/?t=\(token)"
    }

    // MARK: Stop key
    func setStopKey(_ name: String) {
        switch KeyCodes.validateStopKey(name) {
        case .failure(let e): stopKeyMessage = e.message
        case .success(let code):
            if hotKey.register(keyCode: UInt32(code)) {
                stopKeyName = name.lowercased(); stopKeyMessage = nil
                store.set("app.emergency_stop_key", stopKeyName); try? store.save()
            } else { stopKeyMessage = "macOS would not register that key. Try another." }
        }
    }
}
