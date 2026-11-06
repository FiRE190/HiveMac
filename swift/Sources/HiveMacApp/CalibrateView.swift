import SwiftUI
import HiveMacCore
import HiveMacPlatform

struct CalibrateView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                SectionTitle("Permissions")
                PermissionRow(title: "Screen Recording", ok: model.permissions.screenRecording,
                              why: "Lets HiveMac read the backpack and health bars.", pane: .screenRecording)
                PermissionRow(title: "Accessibility", ok: model.permissions.accessibility,
                              why: "Lets HiveMac press keys. Without it macOS silently drops every key.", pane: .accessibility)
                HStack(spacing: Theme.s2) {
                    if !model.permissions.allGranted { Button("Ask macOS") { model.requestPermissions() }.buttonStyle(QuietButtonStyle()) }
                    Button("Check again") { model.refreshPermissions() }.buttonStyle(QuietButtonStyle())
                }
                .padding(.top, Theme.s2)
                Text("After turning something on, quit and reopen HiveMac.").font(Theme.caption).foregroundStyle(Theme.dust).padding(.top, Theme.s1)

                SectionTitle("Roblox")
                HStack(spacing: Theme.s3) {
                    HexDot(color: model.live.windowFound ? Theme.leaf : Theme.ember)
                    Text(model.live.windowText).font(Theme.body).foregroundStyle(Theme.wax)
                    Spacer()
                    Button("Detect Roblox") { model.detectRoblox() }.buttonStyle(HoneyButtonStyle())
                }
                .frame(minHeight: Theme.rowHeight)
                Text("Open Roblox in a window and stand in your hive. Detect sets the backpack, health and hive spots from Natro's defaults.")
                    .font(Theme.caption).foregroundStyle(Theme.dust).fixedSize(horizontal: false, vertical: true)

                SectionTitle("What HiveMac reads right now")
                if model.live.calibrated {
                    readingRow("Backpack", model.live.backpack.map { "\($0) percent" } ?? "no bar colour at that spot",
                               extra: model.live.backpackRGB)
                    readingRow("Health bar", model.live.healthGrey.map { $0 ? "grey (dead)" : "normal" } ?? "not read")
                    readingRow("Hive prompt", model.live.hivePrompt.map { $0 ? "seen" : "not seen" } ?? "no template set, assumed at the hive")
                    Text("Gather a little by hand: the backpack reading should follow the bar in the game.")
                        .font(Theme.caption).foregroundStyle(Theme.dust).padding(.top, Theme.s2)
                } else {
                    Text("Press Detect Roblox first.").font(Theme.body).foregroundStyle(Theme.resin).frame(minHeight: Theme.rowHeight, alignment: .leading)
                }
            }
            .padding(.horizontal, Theme.s6).padding(.bottom, Theme.s6)
        }
        .onAppear { model.refreshLive() }
    }

    private func readingRow(_ label: String, _ value: String, extra: String? = nil) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: Theme.s4) {
            Text(label).font(Theme.body).foregroundStyle(Theme.resin).frame(width: 110, alignment: .leading)
            Text(value).font(Theme.figure).foregroundStyle(Theme.wax)
            if let extra { Text(extra).font(Theme.caption).foregroundStyle(Theme.dust) }
            Spacer()
        }
        .frame(minHeight: 28)
    }
}

struct PermissionRow: View {
    var title: String
    var ok: Bool
    var why: String
    var pane: Permissions.Pane

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: Theme.s3) {
            HexDot(color: ok ? Theme.leaf : Theme.ember)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Theme.bodyStrong).foregroundStyle(Theme.wax)
                Text(ok ? "On" : why).font(Theme.caption).foregroundStyle(ok ? Theme.dust : Theme.resin).fixedSize(horizontal: false, vertical: true)
            }
            Spacer()
            if !ok { Button("Open System Settings") { Permissions.openSettings(pane) }.buttonStyle(QuietButtonStyle()) }
        }
        .frame(minHeight: Theme.rowHeight + 8)
    }
}
