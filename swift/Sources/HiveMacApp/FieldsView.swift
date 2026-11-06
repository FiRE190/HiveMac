import SwiftUI
import HiveMacCore

struct FieldsView: View {
    @EnvironmentObject var model: AppModel
    @State private var renaming = false
    @State private var nameDraft = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: Theme.s2) {
                Choice(options: model.runs.map { ($0.file, $0.name) },
                       selection: Binding(get: { model.activeRunFile }, set: { model.switchRun($0) }), width: 200)
                    .disabled(model.running)
                Menu {
                    Button("New run") { model.addRun(named: nextName(), copying: nil); begin() }
                    Button("Duplicate this run") { model.addRun(named: model.profile.name + " copy", copying: model.profile); begin() }
                    Button("Rename") { begin() }
                    Divider()
                    Button("Delete this run") { model.deleteRun() }.disabled(!model.canDeleteRun)
                } label: { Text("Manage") }
                .menuStyle(.button).buttonStyle(QuietButtonStyle()).fixedSize().disabled(model.running)
                Spacer()
            }
            .padding(.horizontal, Theme.s6).padding(.top, Theme.s4)
            .alert("Name this run", isPresented: $renaming) {
                TextField("Name", text: $nameDraft)
                Button("Save") { model.renameRun(nameDraft) }
                Button("Cancel", role: .cancel) {}
            }

            HStack(spacing: Theme.s2) {
                Color.clear.frame(width: 24, height: 1)
                Text("Field").frame(width: 100, alignment: .leading)
                Text("Minutes").frame(width: 56, alignment: .leading)
                Text("Pack %").frame(width: 56, alignment: .leading)
                Text("Return").frame(width: 76, alignment: .leading)
                Text("Travel").frame(width: 88, alignment: .leading)
                Text("Pattern").frame(width: 132, alignment: .leading)
            }
            .font(Theme.caption).foregroundStyle(Theme.dust)
            .padding(.horizontal, Theme.s6).padding(.top, Theme.s4).padding(.bottom, Theme.s1)

            ScrollView {
                VStack(spacing: 0) {
                    ForEach($model.profile.fields.indices, id: \.self) { i in
                        FieldRow(field: $model.profile.fields[i]) {
                            model.profile.fields.remove(at: i)
                        }
                        Divider().overlay(Theme.grain.opacity(0.6))
                    }
                }
                .padding(.horizontal, Theme.s6)
            }

            HStack {
                Menu {
                    ForEach(FieldDefaults.order, id: \.self) { name in
                        Button(name.capitalized) {
                            var f = FieldConfig(name: name)
                            f.backpackPercent = model.hive.backpackPercent
                            model.profile.fields.append(f)
                        }
                        .disabled(model.profile.fields.contains { $0.name == name })
                    }
                    Divider()
                    Button("Bug run (later)") {}.disabled(true)
                    Button("Planter check (later)") {}.disabled(true)
                } label: { Text("Add to run") }
                .menuStyle(.button).buttonStyle(QuietButtonStyle()).fixedSize()
                Spacer()
                Text("Top to bottom, \(roundMinutes) per round, then it starts again.").font(Theme.caption).foregroundStyle(Theme.dust)
            }
            .padding(Theme.s4)
        }
        .onChange(of: model.profile) { _, _ in model.saveProfile() }
    }
}

extension FieldsView {
    var roundMinutes: String {
        let m = model.profile.fields.filter(\.enabled).reduce(0) { $0 + $1.minutes }
        return m >= 120 ? String(format: "%.1f h", m / 60) : "\(Int(m.rounded())) min"
    }
    func begin() { nameDraft = model.profile.name; renaming = true }
    func nextName() -> String { "Run \(model.runs.count + 1)" }
}

struct FieldRow: View {
    @Binding var field: FieldConfig
    var remove: () -> Void
    @State private var open = ProcessInfo.processInfo.environment["HIVEMAC_OPEN"] != nil

    private static let locations = ["center", "upper left", "upper", "upper right", "left", "right", "lower left", "lower", "lower right"]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: Theme.s2) {
                Toggle("", isOn: $field.enabled).toggleStyle(.checkbox).labelsHidden().frame(width: 24)
                Button { open.toggle() } label: {
                    HStack(spacing: Theme.s1) {
                        Image(systemName: open ? "chevron.down" : "chevron.right").font(.system(size: 9, weight: .bold)).frame(width: 10)
                        Text(field.name.capitalized).font(Theme.body)
                            .foregroundStyle(field.enabled ? Theme.wax : Theme.dust)
                    }
                    .frame(width: 100, alignment: .leading)
                }
                .buttonStyle(.plain).help("Show every option for this field")
                TextField("", value: $field.minutes, format: .number).fieldStyle(width: 56)
                TextField("", value: $field.backpackPercent, format: .number).fieldStyle(width: 56)
                Choice(options: [("walk", "Walk"), ("reset", "Reset")], selection: $field.returnMethod, width: 76)
                Choice(options: [("default", "Default"), ("walk", "Walk"), ("cannon", "Cannon")], selection: $field.travel, width: 88)
                Choice(options: Patterns.names.map { ($0, Self.pretty($0)) }, selection: $field.pattern, width: 132)
                Spacer(minLength: 0)
                Button(action: remove) { Image(systemName: "minus.circle") }
                    .buttonStyle(.plain).foregroundStyle(Theme.dust).help("Remove this field")
            }
            .frame(height: Theme.rowHeight + 4)

            if open { more.padding(.leading, 34).padding(.bottom, Theme.s3) }
        }
    }

    private static func pretty(_ s: String) -> String { s.replacingOccurrences(of: "_", with: " ").capitalized }

    private var more: some View {
        Grid(alignment: .leading, horizontalSpacing: Theme.s3, verticalSpacing: Theme.s2) {
            GridRow {
                label("Size")
                Choice(options: ["xs", "s", "m", "l", "xl"].map { ($0, $0.uppercased()) }, selection: $field.size, width: 76)
                label("Width")
                TextField("", value: $field.width, format: .number).fieldStyle(width: 56)
            }
            GridRow {
                label("Camera")
                Choice(options: [("none", "None"), ("left", "Left"), ("right", "Right")], selection: $field.camera, width: 76)
                label("Turns")
                TextField("", value: $field.turns, format: .number).fieldStyle(width: 56)
            }
            GridRow {
                label("Sprinkler")
                Choice(options: Self.locations.map { ($0, $0.capitalized) }, selection: $field.sprinklerLocation, width: 110)
                label("Distance")
                TextField("", value: $field.sprinklerDistance, format: .number).fieldStyle(width: 56)
            }
            GridRow {
                Color.clear.frame(width: 1, height: 1)
                Toggle("Shift lock", isOn: $field.shiftLock).toggleStyle(.checkbox).font(Theme.body)
                Toggle("Flip forward and back", isOn: $field.invertFB).toggleStyle(.checkbox).font(Theme.body).gridCellColumns(2)
            }
            GridRow {
                Color.clear.frame(width: 1, height: 1)
                Toggle("Flip left and right", isOn: $field.invertLR).toggleStyle(.checkbox).font(Theme.body).gridCellColumns(2)
                Button("Natro defaults") {
                    var d = FieldConfig(name: field.name)
                    d.enabled = field.enabled; d.minutes = field.minutes; d.backpackPercent = field.backpackPercent
                    d.returnMethod = field.returnMethod; d.travel = field.travel
                    field = d
                }.buttonStyle(QuietButtonStyle()).help("Put pattern, size, camera and sprinkler back to Natro's values for this field")
            }
        }
    }

    private func label(_ t: String) -> some View { Text(t).font(Theme.caption).foregroundStyle(Theme.dust) }
}
