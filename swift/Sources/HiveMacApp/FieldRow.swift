import SwiftUI
import HiveMacCore

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
