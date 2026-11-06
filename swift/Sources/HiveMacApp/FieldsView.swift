import SwiftUI
import HiveMacCore

struct FieldsView: View {
    @EnvironmentObject var model: AppModel
    @State private var renaming = false
    @State private var nameDraft = ""
    @StateObject private var reorder = Reorder()

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

            HiveSlotPicker()
                .padding(.horizontal, Theme.s6).padding(.top, Theme.s3)

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
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(model.profile.orderKeys, id: \.self) { key in
                        VStack(spacing: 0) {
                            rowView(key)
                            Divider().overlay(Theme.grain.opacity(0.6))
                        }
                        .background(GeometryReader { g in
                            Color.clear.preference(key: RowFrames.self, value: [key: g.frame(in: .named("rows"))])
                        })
                        .background(reorder.dragging == key ? Theme.plank.opacity(0.9) : Color.clear)
                        .offset(y: reorder.offset(for: key))
                        .zIndex(reorder.dragging == key ? 1 : 0)
                        .shadow(color: .black.opacity(reorder.dragging == key ? 0.35 : 0), radius: 8, y: 2)
                    }
                    if !model.profile.extras.isEmpty {
                        Text("Bug runs, planters and pickups are saved with this run. HiveMac does not run them yet.")
                            .font(Theme.caption).foregroundStyle(Theme.dust).frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                .padding(.horizontal, Theme.s6)
                .coordinateSpace(name: "rows")
                .onPreferenceChange(RowFrames.self) { reorder.frames = $0 }
            }
            .environmentObject(reorder)

            HStack {
                Menu {
                    Menu("Field") {
                        ForEach(FieldDefaults.order, id: \.self) { name in
                            Button(name.capitalized + (!FieldColors.recommended(for: model.hive.color).isEmpty && FieldColors.table[name] == model.hive.color ? "  (fits your bees)" : "")) {
                                var f = FieldConfig(name: name)
                                f.backpackPercent = model.hive.backpackPercent
                                model.profile.fields.append(f)
                            }
                            .disabled(model.profile.fields.contains { $0.name == name })
                        }
                    }
                    Button("Bug run") { model.profile.extras.append(ExtraStep(kind: "bug_run")) }
                    Button("Clock and dispensers") { model.profile.extras.append(ExtraStep(kind: "pickups")) }
                    Button("Planters") { model.profile.extras.append(ExtraStep(kind: "planters")) }
                } label: { Text("Add") }
                .menuStyle(.button).buttonStyle(QuietButtonStyle()).fixedSize()
                Spacer()
                Text("Round: \(roundMinutes)").font(Theme.caption).foregroundStyle(Theme.dust)
            }
            .padding(Theme.s4)
        }
        .onChange(of: model.profile) { _, _ in model.saveProfile() }
        .onAppear { reorder.move = { k, t in model.profile.move(k, before: t) }; reorder.keys = { model.profile.orderKeys } }
    }
}

extension FieldsView {
    @ViewBuilder func rowView(_ key: String) -> some View {
        if key.hasPrefix("f:"), let i = model.profile.fields.firstIndex(where: { "f:" + $0.name == key }) {
            FieldRow(field: $model.profile.fields[i], key: key) { model.profile.fields.remove(at: i) }
        } else if let i = model.profile.extras.firstIndex(where: { "e:" + $0.id.uuidString == key }) {
            ExtraRow(step: $model.profile.extras[i], key: key) { model.profile.extras.remove(at: i) }
        }
    }
    var roundMinutes: String {
        let m = model.profile.fields.filter(\.enabled).reduce(0) { $0 + $1.minutes }
        let base = m >= 120 ? String(format: "%.1f h", m / 60) : "\(Int(m.rounded())) min"
        let extras = model.profile.extras.filter(\.enabled).count
        return extras == 0 ? base : base + " in fields, plus \(extras) extra step\(extras == 1 ? "" : "s")"
    }
    func begin() { nameDraft = model.profile.name; renaming = true }
    func nextName() -> String { "Run \(model.runs.count + 1)" }
}

