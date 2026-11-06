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

            VStack(alignment: .leading, spacing: Theme.s1) {
                HiveSlotPicker()
                Text("Needs the Red Cannon and the Glider (Mountain Top Shop, the upgrade of the Parachute). The walking routes use both.")
                    .font(Theme.caption).foregroundStyle(Theme.dust)
            }
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
                        .offset(y: reorder.dragging == key ? reorder.offset(for: key) : 0)
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
        .onAppear { reorder.move = { k, t in withAnimation(.snappy(duration: 0.18)) { model.profile.move(k, before: t) } }; reorder.keys = { model.profile.orderKeys } }
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
        return m >= 120 ? String(format: "%.1f h", m / 60) : "\(Int(m.rounded())) min"
    }
    func begin() { nameDraft = model.profile.name; renaming = true }
    func nextName() -> String { "Run \(model.runs.count + 1)" }
}

struct FieldRow: View {
    @Binding var field: FieldConfig
    var key: String
    var remove: () -> Void
    @State private var open = ProcessInfo.processInfo.environment["HIVEMAC_OPEN"] != nil

    private static let locations = ["center", "upper left", "upper", "upper right", "left", "right", "lower left", "lower", "lower right"]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: Theme.s2) {
                DragHandle(key: key)
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
                    .buttonStyle(.plain).foregroundStyle(Theme.ember).help("Remove this field")
            }
            .frame(height: Theme.rowHeight + 4)

            if open { more.padding(.leading, 34).padding(.bottom, Theme.s3) }
        }
    }

    private static func pretty(_ s: String) -> String { s.replacingOccurrences(of: "_", with: " ").capitalized }

    /// Changing the size scales the sprinkler distance with it, so the sprinkler stays in the same
    /// place relative to the pattern.
    private var sizeBinding: Binding<String> {
        Binding(get: { field.size }, set: { new in
            let ratio = Patterns.sizeFactor(new) / Patterns.sizeFactor(field.size)
            field.sprinklerDistance = max(1, Int((Double(field.sprinklerDistance) * ratio).rounded()))
            field.size = new
        })
    }

    private var more: some View {
        Grid(alignment: .leading, horizontalSpacing: Theme.s3, verticalSpacing: Theme.s2) {
            GridRow {
                Color.clear.frame(width: 1, height: 1)
                Toggle("Use this field", isOn: $field.enabled).toggleStyle(.checkbox).font(Theme.body).gridCellColumns(3)
            }
            GridRow {
                label("Size")
                Choice(options: ["xs", "s", "m", "l", "xl"].map { ($0, $0.uppercased()) }, selection: sizeBinding, width: 76)
                Text("Sets how far the pattern spreads. The sprinkler distance follows it.")
                    .font(Theme.caption).foregroundStyle(Theme.dust).gridCellColumns(2)
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
                label("Repeats")
                TextField("", value: $field.width, format: .number).fieldStyle(width: 56)
                Text("How many times the pattern repeats.").font(Theme.caption).foregroundStyle(Theme.dust).gridCellColumns(2)
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


struct ExtraRow: View {
    @EnvironmentObject var model: AppModel
    @Binding var step: ExtraStep
    var key: String
    var remove: () -> Void
    @State private var open = true

    private var title: String { step.kind == "planters" ? "Planters" : step.kind == "pickups" ? "Clock and dispensers" : "Bug run" }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.s2) {
            HStack(spacing: Theme.s2) {
                DragHandle(key: key)
                Button { open.toggle() } label: {
                    HStack(spacing: Theme.s1) {
                        Image(systemName: open ? "chevron.down" : "chevron.right").font(.system(size: 9, weight: .bold)).frame(width: 10)
                        Text(title).font(Theme.body).foregroundStyle(step.enabled ? Theme.wax : Theme.dust)
                    }
                }.buttonStyle(.plain)
                Spacer()
                Button(action: remove) { Image(systemName: "minus.circle") }.buttonStyle(.plain).foregroundStyle(Theme.ember).help("Remove this step")
            }
            .frame(height: Theme.rowHeight)
            if open {
                VStack(alignment: .leading, spacing: Theme.s2) {
                    Toggle("Use this step", isOn: $step.enabled).toggleStyle(.checkbox).font(Theme.body)
                    if step.kind == "planters" { planters } else { bugRun }
                }.padding(.leading, 34).padding(.bottom, Theme.s3)
            }
        }
    }

    private var bugRun: some View {
        VStack(alignment: .leading, spacing: Theme.s2) {
            Text(step.kind == "pickups" ? "Each one is only collected once its own timer has run out." : "A mob is only visited once its own timer has run out.").font(Theme.caption).foregroundStyle(Theme.dust)
            ForEach(step.kind == "pickups" ? MobTimers.pickups : ExtraStep.bugs, id: \.self) { bug in
                HStack(spacing: Theme.s3) {
                    Toggle(bug.capitalized, isOn: Binding(
                        get: { step.bugs.contains(bug) },
                        set: { on in
                            if on { if !step.bugs.contains(bug) { step.bugs.append(bug) } } else { step.bugs.removeAll { $0 == bug } }
                        })).toggleStyle(.checkbox).font(Theme.body).frame(width: 150, alignment: .leading)
                    let timed = MobTimers.respawn[bug] != nil
                    let left = model.mobTimers.remaining(bug, now: Date().timeIntervalSince1970)
                    Text(MobTimers.describe(remaining: left, timed: timed)).font(Theme.caption)
                        .foregroundStyle(timed && left == 0 ? Theme.leaf : Theme.dust)
                    Spacer(minLength: 0)
                    if let wait = MobTimers.respawn[bug] {
                        Text((step.kind == "pickups" ? "every " : "respawns every ") + (wait < 3600 ? "\(Int(wait / 60)) min" : "\(Int(wait / 3600)) h"))
                            .font(Theme.caption).foregroundStyle(Theme.dust)
                    }
                }
            }
        }
    }

    private var planters: some View {
        VStack(alignment: .leading, spacing: Theme.s2) {
            Text("Each slot has its own timer. A round only visits slots that are grown and skips the rest.")
                .font(Theme.caption).foregroundStyle(Theme.dust)
            ForEach(0..<3, id: \.self) { i in
                HStack(spacing: Theme.s2) {
                    Text("Slot \(i + 1)").font(Theme.caption).foregroundStyle(Theme.dust).frame(width: 44, alignment: .leading)
                    Choice(options: [("", "None")] + FieldDefaults.order.map { ($0, $0.capitalized) },
                           selection: $step.planterFields[i], width: 140)
                    Choice(options: ExtraStep.planters.map { ($0, $0.capitalized) },
                           selection: $step.planterTypes[i], width: 150)
                        .disabled(step.planterFields[i].isEmpty)
                }
                HStack(spacing: Theme.s3) {
                    Color.clear.frame(width: 44, height: 1)
                    Toggle("Replant after harvest", isOn: $step.planterReplant[i]).toggleStyle(.checkbox).font(Theme.body)
                    let left = step.planterRemaining(i, now: Date().timeIntervalSince1970)
                    Text(left == nil ? "Empty" : left == 0 ? "Ready" : "Ready in " + MobTimers.describeDuration(left ?? 0))
                        .font(Theme.caption).foregroundStyle(left == 0 ? Theme.leaf : Theme.dust)
                    Spacer(minLength: 0)
                    Button("Planted now") { step.planterPlanted[i] = Date().timeIntervalSince1970 }
                        .buttonStyle(QuietButtonStyle()).disabled(step.planterFields[i].isEmpty)
                        .help("Start this slot's timer, for a planter you just put down")
                }
            }
            HStack(spacing: Theme.s2) {
                Text("Grows for").font(Theme.caption).foregroundStyle(Theme.dust)
                TextField("", value: $step.harvestHours, format: .number).fieldStyle(width: 56)
                Text("hours").font(Theme.caption).foregroundStyle(Theme.dust)
            }
        }
    }
}


/// Which of the six hive spots in the Bee Swarm lobby is yours. The walk to and from every field
/// starts at this slot, so a wrong choice sends the character the wrong way.
struct HiveSlotPicker: View {
    @EnvironmentObject var model: AppModel

    private var slot: Int { _ = model.settingsVersion; return model.store.int("game.hive_slot", 1) }

    var body: some View {
        HStack(spacing: Theme.s2) {
            Text("My hive").font(Theme.body).foregroundStyle(Theme.resin)
            ForEach(1...6, id: \.self) { n in
                Button { model.set("game.hive_slot", n) } label: {
                    Text("\(n)")
                        .font(Theme.bodyStrong).monospacedDigit()
                        .frame(width: 32, height: 28)
                        .foregroundStyle(slot == n ? Theme.onHoney : Theme.wax)
                        .background(RoundedRectangle(cornerRadius: Theme.controlRadius)
                            .fill(slot == n ? Theme.honey : Theme.plank))
                        .overlay(RoundedRectangle(cornerRadius: Theme.controlRadius)
                            .stroke(slot == n ? Color.clear : Theme.grain, lineWidth: 1))
                }
                .buttonStyle(.plain)
                .disabled(model.running)
                .accessibilityLabel("Hive slot \(n)")
            }
            Spacer()
        }
    }
}


struct RowFrames: PreferenceKey {
    static var defaultValue: [String: CGRect] = [:]
    static func reduce(value: inout [String: CGRect], nextValue: () -> [String: CGRect]) { value.merge(nextValue()) { $1 } }
}

/// Live drag-to-reorder. The dragged row follows the pointer; the others slide out of the way.
final class Reorder: ObservableObject {
    @Published var dragging: String?
    @Published var pointerY: CGFloat = 0
    var grab: CGFloat = 0
    var frames: [String: CGRect] = [:]
    var move: (String, String?) -> Void = { _, _ in }
    var keys: () -> [String] = { [] }

    func offset(for key: String) -> CGFloat {
        guard let f = frames[key] else { return 0 }
        return pointerY - grab - f.midY
    }

    func changed(_ key: String, y: CGFloat) {
        if dragging == nil, let f = frames[key] { dragging = key; grab = y - f.midY }
        guard dragging == key, let me = frames[key] else { return }
        pointerY = y
        let order = keys()
        guard let idx = order.firstIndex(of: key) else { return }
        let center = y - grab
        if idx > 0, let up = frames[order[idx - 1]], center < up.midY {
            move(key, order[idx - 1])
        } else if idx + 1 < order.count, let down = frames[order[idx + 1]], center > down.midY {
            move(key, idx + 2 < order.count ? order[idx + 2] : nil)
        }
        _ = me
    }

    func ended() { withAnimation(.snappy(duration: 0.18)) { dragging = nil } }
}

/// The grip at the left of every row. Drag it up or down to change the order.
struct DragHandle: View {
    let key: String
    @EnvironmentObject var reorder: Reorder
    var body: some View {
        Image(systemName: "line.3.horizontal")
            .font(.system(size: 12, weight: .semibold)).foregroundStyle(reorder.dragging == key ? Theme.honeyText : Theme.dust)
            .frame(width: 24, height: 28).contentShape(Rectangle())
            .gesture(DragGesture(minimumDistance: 2, coordinateSpace: .named("rows"))
                .onChanged { reorder.changed(key, y: $0.location.y) }
                .onEnded { _ in reorder.ended() })
            .help("Drag to change the order")
    }
}
