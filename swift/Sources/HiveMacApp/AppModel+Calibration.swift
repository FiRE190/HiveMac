import SwiftUI
import AppKit
import HiveMacCore
import HiveMacPlatform

extension AppModel {
    // MARK: Calibration tools: record a walk, capture a picture
    func userWalkURL(kind: String, field: String) -> URL {
        dirs.userPaths.appendingPathComponent("\(kind)/\(Paths.fieldSlug(field)).json")
    }

    func toggleRecording(kind: String, field: String) {
        if !recording {
            guard !running else { calibMessage = "Stop the macro first."; return }
            guard Permissions.inputMonitoring else {
                Permissions.requestInputMonitoring()
                calibMessage = "Turn on Input Monitoring for HiveMac in System Settings, then reopen HiveMac. It is only used to record walks."
                return
            }
            keyRecorder.start(); recording = true
            calibMessage = kind == "to_field" ? "Recording. Walk from the hive to the field, then press Stop where gathering should start."
                                              : "Recording. Walk from the field back to the hive, then press Stop at the hive."
            return
        }
        let events = keyRecorder.stop(); recording = false
        let speed = store.double("game.walk_speed", 28)
        let steps = Recorder.steps(from: events, walkSpeed: speed)
        guard !steps.isEmpty else { calibMessage = "Nothing recorded."; return }
        var file = PathFile(name: Paths.fieldSlug(field), steps: steps)
        file.source = "recorded in HiveMac"; file.walkSpeed = speed
        do {
            try file.save(to: userWalkURL(kind: kind, field: field))
            calibMessage = "Saved your walk for \(field.capitalized) (\(steps.count) steps). It replaces Natro's."
        } catch { calibMessage = "Could not save: \(error.localizedDescription)" }
    }

    func removeUserWalk(kind: String, field: String) {
        let u = userWalkURL(kind: kind, field: field)
        if FileManager.default.fileExists(atPath: u.path) {
            try? FileManager.default.removeItem(at: u)
            calibMessage = "Removed your walk for \(field.capitalized). Natro's walk is used again."
        } else { calibMessage = "No walk of your own for \(field.capitalized). Natro's is already used." }
    }

    /// The Roblox window right now, for picking a picture out of it.
    func snapshotRoblox() -> RGBImage? {
        robloxBounds.flatMap { capture.grab($0) }
    }

    /// Saves the chosen rectangle (in snapshot pixels) as a template and points the HUD at it.
    func saveTemplate(key: String, from snapshot: RGBImage, x: Int, y: Int, w: Int, h: Int) {
        guard let crop = snapshot.cropped(x: x, y: y, width: w, height: h), crop.width >= 4, crop.height >= 4 else {
            calibMessage = "That area is too small."; return
        }
        let name = "\(key).png"
        guard ScreenCapture.savePNG(crop, to: dirs.templates.appendingPathComponent(name)) else { calibMessage = "Could not save the picture."; return }
        store.set("hud.\(key)_template", name)
        if key != "cannon_prompt" {                                        // the cannon prompt looks in the hive prompt area
            let pad = 24
            let rx = max(0, x - pad), ry = max(0, y - pad)
            let rw = min(snapshot.width - rx, w + 2 * pad), rh = min(snapshot.height - ry, h + 2 * pad)
            store.set("hud.\(key)_region", ["fx": Double(rx) / Double(snapshot.width), "fy": Double(ry) / Double(snapshot.height),
                                             "fw": Double(rw) / Double(snapshot.width), "fh": Double(rh) / Double(snapshot.height)])
        }
        store.set("hud.calibrated", true)
        try? store.save()
        calibMessage = "Saved \(name) (\(crop.width) by \(crop.height))."
        append("Calibrate: saved \(name)")
        refreshLive()
    }

    // MARK: Calibration
    func refreshPermissions() { if !isDemo { permissions = Permissions.current() } }

    /// Finds Roblox and seeds the HUD spots with Natro's defaults where nothing is set yet.
    func detectRoblox() {
        guard let w = robloxBounds else {
            append("Detect Roblox: no Roblox window found. Open it first.")
            refreshLive(); return
        }
        let d = Layout.natroDefaults(w)
        func pt(_ p: RelPoint) -> [String: Any] { ["fx": p.fx, "fy": p.fy] }
        func rg(_ r: RelRegion) -> [String: Any] { ["fx": r.fx, "fy": r.fy, "fw": r.fw, "fh": r.fh] }
        let seeds: [(String, Any)] = [("backpack_pixel", pt(d.backpackPixel)), ("health_pixel", pt(d.healthPixel)),
                                      ("hive_prompt_region", rg(d.hivePromptRegion)), ("hive_view_region", rg(d.hiveViewRegion)),
                                      ("hive_strip_region", rg(d.hiveStripRegion))]
        for (key, value) in seeds where store.get("hud.\(key)") == nil || store.get("hud.\(key)") is NSNull {
            store.set("hud.\(key)", value)
        }
        store.set("hud.calibrated", true)
        try? store.save()
        append("Detect Roblox: window \(w.width) by \(w.height). HUD spots set from Natro's defaults.")
        refreshLive()
    }

    // MARK: Live readings (a light poll while idle, so the gauge and Calibrate tab show real values)
    func startPolling() {
        let t = DispatchSource.makeTimerSource(queue: pollQueue)
        t.schedule(deadline: .now() + 1, repeating: 2, leeway: .milliseconds(500))
        t.setEventHandler { [weak self] in
            DispatchQueue.main.async { if let self, !self.running, NSApp.isActive { self.refreshLive() } }
        }
        t.activate()
        pollTimer = t
    }

    func refreshLive() {
        if isDemo { return }
        permissions = Permissions.current()
        let store = self.store, capture = self.capture, dirs = self.dirs
        let allowed = permissions.screenRecording
        pollQueue.async { [weak self] in
            var r = LiveReadings()
            let win = Self.bounds(store)
            r.windowFound = win != nil
            r.windowText = win.map { "Roblox found, \($0.width) by \($0.height)" } ?? "Roblox not found"
            r.calibrated = store.bool("hud.calibrated")
            if allowed, let win, r.calibrated {
                let hud = HudConfig(store: store) { ScreenCapture.loadPNG(dirs.templates.appendingPathComponent($0)) }
                let s = ScreenSensors(screen: capture, window: { win }, config: hud)
                if let raw = s.backpackRaw() { r.backpack = raw }
                if let c = s.lastBackpackRGB { r.backpackRGB = "rgb(\(c.r), \(c.g), \(c.b))" }
                r.healthGrey = s.healthGrey()
                r.hivePrompt = s.hivePromptVisible()
            }
            DispatchQueue.main.async {
                guard let self else { return }
                self.live = r
                if !self.running { self.backpack = r.backpack }
            }
        }
    }
}
