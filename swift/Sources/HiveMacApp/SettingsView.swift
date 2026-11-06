import SwiftUI
import AppKit
import HiveMacCore

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
                SettingRow(label: "Hive color", hint: "Sets which fields match your bees.") {
                    Picker("", selection: $model.hive.color) {
                        Text("Blue").tag("blue"); Text("Red").tag("red"); Text("White").tag("white"); Text("Mixed").tag("mixed")
                    }.labelsHidden().frame(width: 110)
                }
                SettingRow(label: "Bees") { TextField("", value: $model.hive.beeCount, format: .number).fieldStyle(width: 64) }
                SettingRow(label: "Average bee level") { TextField("", value: $model.hive.avgBeeLevel, format: .number).fieldStyle(width: 64) }
                SettingRow(label: "Cub Buddy", hint: "The bear that picks up tokens for you.") { Toggle("I have it", isOn: $model.hive.cubBuddy).toggleStyle(.checkbox) }
                SettingRow(label: "Backpack percent", hint: "Default for new fields.") { TextField("", value: $model.hive.backpackPercent, format: .number).fieldStyle(width: 64) }
                SettingRow(label: "Hive slot", hint: "Counted from the ramp.") {
                    Picker("", selection: int("game.hive_slot", 1)) { ForEach(1...6, id: \.self) { Text("\($0)").tag($0) } }.labelsHidden().frame(width: 70)
                }

                SectionTitle("Walking")
                SettingRow(label: "Walk speed", hint: "From the in-game settings panel. Natro's default is 28.") {
                    TextField("", value: num("game.walk_speed", 28), format: .number).fieldStyle(width: 64)
                }
                SettingRow(label: "Default travel") {
                    Picker("", selection: str("game.travel", "walk")) { Text("Walk").tag("walk"); Text("Cannon").tag("cannon") }.labelsHidden().frame(width: 110)
                }
                SettingRow(label: "Roblox window", hint: "Windowed is the simple one. Keep its size fixed.") {
                    Picker("", selection: str("game.window_mode", "windowed")) { Text("Windowed").tag("windowed"); Text("Full screen").tag("fullscreen") }.labelsHidden().frame(width: 130)
                }
                SettingRow(label: "Sprinkler") {
                    Picker("", selection: str("game.sprinkler_type", "none")) {
                        ForEach(Sprinkler.types, id: \.self) { Text($0.capitalized).tag($0) }
                    }.labelsHidden().frame(width: 110)
                }
                SettingRow(label: "Sprinkler hotbar key") {
                    Picker("", selection: str("game.sprinkler_slot_key", "1")) { ForEach(1...7, id: \.self) { Text("\($0)").tag("\($0)") } }.labelsHidden().frame(width: 70)
                }

                SectionTitle("Stop key")
                SettingRow(label: "Stop everything", hint: "Works in any app. On some keyboards F keys need Fn held.") {
                    StopKeyField()
                }
                if let msg = model.stopKeyMessage {
                    Text(msg).font(Theme.caption).foregroundStyle(Theme.ember).padding(.leading, 206)
                }

                SectionTitle("Data")
                SettingRow(label: "Folder", hint: model.dirs.data.path) {
                    Button("Show in Finder") { NSWorkspace.shared.activateFileViewerSelecting([model.dirs.data]) }.buttonStyle(QuietButtonStyle())
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
    @State private var capturing = false
    @State private var monitor: Any?

    var body: some View {
        Button {
            capturing ? finish() : begin()
        } label: {
            Text(capturing ? "Press a key" : model.stopKeyName.uppercased())
                .frame(minWidth: 90)
        }
        .buttonStyle(QuietButtonStyle(tint: capturing ? Theme.honeyText : Theme.wax))
        .onDisappear { finish() }
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
