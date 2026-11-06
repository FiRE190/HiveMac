import SwiftUI
import AppKit
import HiveMacCore

enum Tab: String, CaseIterable, Identifiable {
    case fields = "Fields", settings = "Macro", calibrate = "Calibrate", log = "Log"
    var id: String { rawValue }
}

struct MainView: View {
    @EnvironmentObject var model: AppModel
    @State private var clickMonitor: Any?
    @State private var tab: Tab = Tab(rawValue: (ProcessInfo.processInfo.environment["HIVEMAC_TAB"] ?? "").capitalized) ?? (ProcessInfo.processInfo.environment["HIVEMAC_TAB"] == "settings" ? .settings : .fields)

    var body: some View {
        VStack(spacing: 0) {
            Color.clear.frame(height: 0).onAppear(perform: installClickAway)
            HeaderView()
            Divider().overlay(Theme.grain)
            VStack(alignment: .leading, spacing: Theme.s3) {
                BackpackBar(percent: model.backpack, active: model.running && !model.paused)
                CountersView()
                if !model.detail.isEmpty && model.state != .idle {
                    Text(model.detail).font(Theme.caption).foregroundStyle(model.state == .error ? Theme.ember : Theme.resin)
                        .lineLimit(2).fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(.horizontal, Theme.s6).padding(.vertical, Theme.s4)
            ControlsView().padding(.horizontal, Theme.s6).padding(.bottom, Theme.s4)
            TabBar(tab: $tab)
            Divider().overlay(Theme.grain)
            Group {
                switch tab {
                case .fields: FieldsView()
                case .settings: SettingsView()
                case .calibrate: CalibrateView()
                case .log: LogView()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Theme.bench)
        }
        .background(Theme.shed)
        .tint(Theme.honey)
        .onAppear {
            model.refreshLive()
            if !model.live.calibrated && ProcessInfo.processInfo.environment["HIVEMAC_TAB"] == nil { tab = .calibrate }
        }
    }
}

struct HeaderView: View {
    @EnvironmentObject var model: AppModel

    private var dot: Color {
        switch model.state {
        case .idle: return Theme.dust
        case .gathering: return Theme.leaf
        case .resetting, .converting, .traveling: return Theme.honey
        case .paused: return Theme.resin
        case .warning: return Theme.honey
        case .error: return Theme.ember
        }
    }

    private var timer: String {
        let s = model.runtimeSeconds
        return String(format: "%d:%02d:%02d", s / 3600, (s / 60) % 60, s % 60)
    }

    @State private var showSettings = ProcessInfo.processInfo.environment["HIVEMAC_SHEET"] != nil

    var body: some View {
        HStack(spacing: Theme.s3) {
            Spacer().frame(width: 68)          // clears the window buttons
            HiveMark(size: 24)
            Text("HiveMac").font(Theme.serif(20, .semibold)).foregroundStyle(Theme.wax)
            Spacer()
            HexDot(color: dot)
            Text(model.state.label).font(Theme.bodyStrong).foregroundStyle(Theme.wax)
            Text(timer).font(Theme.figure).foregroundStyle(Theme.resin)
            Button { showSettings = true } label: { Image(systemName: "gearshape").font(.system(size: 15)) }
                .buttonStyle(.plain).foregroundStyle(Theme.resin).help("App settings")
        }
        .padding(.trailing, Theme.s6)
        .frame(height: 52)
        .sheet(isPresented: $showSettings) { AppSettingsView() }
    }
}

struct BackpackBar: View {
    var percent: Int?
    var active: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: Theme.s2) {
            HStack(alignment: .firstTextBaseline) {
                Text("Backpack").font(Theme.body).foregroundStyle(Theme.resin)
                Spacer()
                Text(percent.map { "\($0)%" } ?? "n/a").font(Theme.figure).foregroundStyle(Theme.wax)
            }
            GeometryReader { g in
                ZStack(alignment: .leading) {
                    Capsule().fill(Theme.plank)
                    Capsule().fill(active ? Theme.honey : Theme.dust)
                        .frame(width: g.size.width * CGFloat(min(100, max(0, percent ?? 0))) / 100)
                }
            }
            .frame(height: 8)
        }
    }
}

struct CountersView: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        HStack(alignment: .top, spacing: Theme.s6) {
            stat("Field", model.currentField.isEmpty ? "None" : model.currentField.capitalized)
            stat("Cycles", "\(model.stats.cycles)")
            stat("Converts", "\(model.stats.converts)")
            stat("Deaths", "\(model.stats.deaths)")
            Spacer(minLength: 0)
        }
    }
    private func stat(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(Theme.caption).foregroundStyle(Theme.dust)
            Text(value).font(Theme.figure).foregroundStyle(Theme.wax)
        }
    }
}

struct ControlsView: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        HStack(spacing: Theme.s2) {
            Button("Start") { model.start() }
                .buttonStyle(HoneyButtonStyle()).disabled(model.running)
                .keyboardShortcut(.return, modifiers: .command)
            Button(model.paused ? "Resume" : "Pause") { model.paused ? model.resume() : model.pause() }
                .buttonStyle(QuietButtonStyle()).disabled(!model.running)
            Button("Stop") { model.stop() }
                .buttonStyle(QuietButtonStyle(tint: Theme.ember)).disabled(!model.running)
            Spacer()
            Text("Stop key").font(Theme.caption).foregroundStyle(Theme.dust)
            StopKeyField(compact: true)
        }
    }
}

extension MainView {
    /// A click anywhere that is not the text being edited ends the edit, like a normal Mac app.
    func installClickAway() {
        guard clickMonitor == nil else { return }
        clickMonitor = NSEvent.addLocalMonitorForEvents(matching: .leftMouseDown) { event in
            guard let window = event.window, let editor = window.firstResponder as? NSTextView, editor.isFieldEditor else { return event }
            let hit = window.contentView?.hitTest(event.locationInWindow)
            if hit !== editor && !(hit?.isDescendant(of: editor) ?? false) { window.makeFirstResponder(nil) }
            return event
        }
    }
}

struct TabBar: View {
    @Binding var tab: Tab
    var body: some View {
        HStack(spacing: Theme.s1) {
            ForEach(Tab.allCases) { t in
                Button { tab = t } label: {
                    Text(t.rawValue).font(Theme.bodyStrong)
                        .foregroundStyle(tab == t ? Theme.honeyText : Theme.resin)
                        .padding(.horizontal, Theme.s3).frame(height: 30)
                        .background(RoundedRectangle(cornerRadius: Theme.controlRadius).fill(tab == t ? Theme.plank : .clear))
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
        .padding(.horizontal, Theme.s4).padding(.bottom, Theme.s2)
    }
}
