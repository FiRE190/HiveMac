import SwiftUI
import AppKit
import HiveMacCore

/// The macro's own settings. App settings (permissions, stop key, updates) are behind the gear.
struct SettingsView: View {
    @EnvironmentObject var model: AppModel

    private func num(_ path: String, _ fallback: Double) -> Binding<Double> {
        Binding(get: { _ = model.settingsVersion; return model.store.double(path, fallback) }, set: { model.set(path, $0) })
    }
    private func int(_ path: String, _ fallback: Int) -> Binding<Int> {
        Binding(get: { _ = model.settingsVersion; return model.store.int(path, fallback) }, set: { model.set(path, $0) })
    }
    private func str(_ path: String, _ fallback: String) -> Binding<String> {
        Binding(get: { _ = model.settingsVersion; return model.store.string(path, fallback) }, set: { model.set(path, $0) })
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                SectionTitle("Hive")
                SettingRow(label: "Hive color") {
                    Choice(options: [("blue", "Blue"), ("red", "Red"), ("white", "White"), ("mixed", "Mixed")],
                           selection: $model.hive.color, width: 120)
                }
                SettingRow(label: "Bees") { TextField("", value: $model.hive.beeCount, format: .number).fieldStyle(width: 64) }
                SettingRow(label: "Average bee level") { TextField("", value: $model.hive.avgBeeLevel, format: .number).fieldStyle(width: 64) }
                SettingRow(label: "Cub Buddy") { Toggle("Have it", isOn: $model.hive.cubBuddy).toggleStyle(.checkbox) }
                SettingRow(label: "Backpack percent") { TextField("", value: $model.hive.backpackPercent, format: .number).fieldStyle(width: 64) }

                SectionTitle("Walking")
                SettingRow(label: "Walk speed, no buffs") { TextField("", value: num("game.walk_speed", 28), format: .number).fieldStyle(width: 64) }
                SettingRow(label: "Default travel") {
                    Choice(options: [("walk", "Walk"), ("cannon", "Cannon")], selection: str("game.travel", "walk"), width: 120)
                }
                SettingRow(label: "Roblox window") {
                    Choice(options: [("windowed", "Windowed"), ("fullscreen", "Full screen")], selection: str("game.window_mode", "windowed"), width: 120)
                }

                SectionTitle("Sprinkler")
                SettingRow(label: "Type") {
                    Choice(options: Sprinkler.types.map { ($0, $0.capitalized) }, selection: str("game.sprinkler_type", "none"), width: 120)
                }
                SettingRow(label: "Hotbar key") {
                    Choice(options: (1...7).map { ("\($0)", "\($0)") }, selection: str("game.sprinkler_slot_key", "1"), width: 64)
                }
            }
            .padding(.horizontal, Theme.s6).padding(.bottom, Theme.s6)
        }
        .onChange(of: model.hive) { _, _ in model.saveSettings() }
    }
}

/// Click, then press the key you want. Keys the macro presses itself are refused.
struct StopKeyField: View {
    @EnvironmentObject var model: AppModel
    var compact = false
    @State private var capturing = false
    @State private var monitor: Any?

    var body: some View {
        if compact {
            Button { capturing ? finish() : begin() } label: {
                Text(capturing ? "Press a key" : model.stopKeyName.uppercased())
                    .font(Theme.figure).foregroundStyle(capturing ? Theme.honeyText : Theme.wax)
                    .padding(.horizontal, Theme.s2).frame(minWidth: 28, minHeight: 24)
                    .background(RoundedRectangle(cornerRadius: 6).fill(Theme.plank))
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(capturing ? Theme.honeyText : Theme.grain, lineWidth: 1))
            }
            .buttonStyle(.plain).help("Click, then press the key you want")
            .onDisappear { finish() }
        } else {
            Button { capturing ? finish() : begin() } label: {
                Text(capturing ? "Press a key" : model.stopKeyName.uppercased()).frame(minWidth: 90)
            }
            .buttonStyle(QuietButtonStyle(tint: capturing ? Theme.honeyText : Theme.wax))
            .onDisappear { finish() }
        }
    }

    private func begin() {
        capturing = true
        model.stopKeyMessage = nil
        monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            if event.keyCode == 53 && model.stopKeyName != "esc" { finish(); return nil }      // Esc cancels
            let name = KeyCodes.name(for: event.keyCode) ?? ""
            model.setStopKey(name)
            finish()
            return nil
        }
    }

    private func finish() {
        capturing = false
        if let monitor { NSEvent.removeMonitor(monitor) }
        monitor = nil
    }
}
