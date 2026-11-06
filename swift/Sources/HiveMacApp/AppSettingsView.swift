import SwiftUI
import AppKit
import HiveMacCore

/// The app itself: permissions, stop key, updates, data. The macro's own settings are in the Macro tab.
struct AppSettingsView: View {
    @EnvironmentObject var model: AppModel
    @EnvironmentObject var updates: UpdateChecker
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Settings").font(Theme.serif(20, .semibold)).foregroundStyle(Theme.wax)
                Spacer()
                Button("Done") { dismiss() }.buttonStyle(HoneyButtonStyle()).keyboardShortcut(.defaultAction)
            }
            .padding(Theme.s6)
            Divider().overlay(Theme.grain)
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    SectionTitle("Permissions")
                    PermissionRow(title: "Screen Recording", ok: model.permissions.screenRecording,
                                  why: "Lets HiveMac read the backpack and health bars.", pane: .screenRecording)
                    PermissionRow(title: "Accessibility", ok: model.permissions.accessibility,
                                  why: "Lets HiveMac press keys.", pane: .accessibility)
                    HStack(spacing: Theme.s3) {
                        Button("Check again") { model.refreshPermissions() }.buttonStyle(QuietButtonStyle())
                        Text("After turning one on, quit and reopen HiveMac.").font(Theme.caption).foregroundStyle(Theme.dust)
                    }.padding(.top, Theme.s2)

                    SectionTitle("Stop key")
                    SettingRow(label: "Stop everything") { StopKeyField() }
                    if let msg = model.stopKeyMessage {
                        Text(msg).font(Theme.caption).foregroundStyle(Theme.ember)
                    }

                    SectionTitle("Updates")
                    UpdateRow(checker: updates)

                    SectionTitle("Data")
                    SettingRow(label: "Folder", hint: model.dirs.data.path) {
                        Button("Show in Finder") { NSWorkspace.shared.activateFileViewerSelecting([model.dirs.data]) }.buttonStyle(QuietButtonStyle())
                    }
                }
                .padding(.horizontal, Theme.s6).padding(.bottom, Theme.s6)
            }
        }
        .frame(width: 520, height: 560)
        .background(Theme.shed)
        .tint(Theme.honey)
    }
}
