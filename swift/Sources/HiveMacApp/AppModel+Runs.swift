import SwiftUI
import AppKit
import HiveMacCore
import HiveMacPlatform

extension AppModel {
    // MARK: Profile and settings
    func saveProfile() {
        try? profile.save(to: dirs.profiles.appendingPathComponent(activeRunFile))
        refreshRuns()
    }

    // MARK: Run library (each run is one profile file)
    struct RunEntry: Identifiable, Equatable { let file: String; let name: String; var id: String { file } }

    func refreshRuns() {
        let files = (try? FileManager.default.contentsOfDirectory(atPath: dirs.profiles.path)) ?? []
        runs = files.filter { $0.hasSuffix(".json") }.sorted().compactMap { f in
            (try? Profile.load(dirs.profiles.appendingPathComponent(f))).map { RunEntry(file: f, name: $0.name) }
        }
    }

    func switchRun(_ file: String) {
        guard !running, file != activeRunFile,
              let p = try? Profile.load(dirs.profiles.appendingPathComponent(file)) else { return }
        activeRunFile = file; profile = p
        set("app.active_run_file", file)
    }

    func newRunFile(_ name: String) -> String {
        let slug = String(name.lowercased().map { $0.isLetter || $0.isNumber ? $0 : "_" })
        var f = "\(slug).json", n = 2
        while FileManager.default.fileExists(atPath: dirs.profiles.appendingPathComponent(f).path) { f = "\(slug)_\(n).json"; n += 1 }
        return f
    }

    /// Creates a run from `base` (a copy of the current one, or nothing for a fresh one) and opens it.
    func addRun(named name: String, copying base: Profile?) {
        guard !running else { return }
        var p = base ?? Profile(fields: [FieldConfig(name: "sunflower")])
        p.name = name
        let f = newRunFile(name)
        try? p.save(to: dirs.profiles.appendingPathComponent(f))
        refreshRuns(); switchRun(f)
    }

    func renameRun(_ name: String) {
        let t = name.trimmingCharacters(in: .whitespaces)
        guard !t.isEmpty else { return }
        profile.name = t
    }

    var canDeleteRun: Bool { runs.count > 1 && !running }

    func deleteRun() {
        guard canDeleteRun else { return }
        let gone = activeRunFile
        try? FileManager.default.removeItem(at: dirs.profiles.appendingPathComponent(gone))
        refreshRuns()
        if let next = runs.first?.file { activeRunFile = ""; switchRun(next) }
    }

    func saveSettings() {
        hive.write(to: store)
        try? store.save()
        settingsVersion += 1
    }

    func set(_ path: String, _ value: Any) { store.set(path, value); try? store.save(); settingsVersion += 1 }
}
