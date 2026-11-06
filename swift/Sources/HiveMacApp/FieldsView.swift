import SwiftUI
import HiveMacCore

struct FieldsView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: Theme.s2) {
                Text("").frame(width: 24)
                Text("Field").frame(width: 130, alignment: .leading)
                Text("Minutes").frame(width: 64, alignment: .trailing)
                Text("Backpack %").frame(width: 84, alignment: .trailing)
                Text("Back to hive").frame(width: 92, alignment: .leading)
                Text("Travel").frame(width: 80, alignment: .leading)
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
                } label: { Text("Add a field") }
                .menuStyle(.button).buttonStyle(QuietButtonStyle()).fixedSize()
                Spacer()
                Text("Fields run in this order, then start again from the top.").font(Theme.caption).foregroundStyle(Theme.dust)
            }
            .padding(Theme.s4)
        }
        .onChange(of: model.profile) { _, _ in model.saveProfile() }
    }
}

struct FieldRow: View {
    @Binding var field: FieldConfig
    var remove: () -> Void

    var body: some View {
        HStack(spacing: Theme.s2) {
            Toggle("", isOn: $field.enabled).toggleStyle(.checkbox).labelsHidden().frame(width: 24)
            Text(field.name.capitalized).font(Theme.body)
                .foregroundStyle(field.enabled ? Theme.wax : Theme.dust).frame(width: 130, alignment: .leading)
            TextField("", value: $field.minutes, format: .number).fieldStyle(width: 64)
            TextField("", value: $field.backpackPercent, format: .number).fieldStyle(width: 84)
            Picker("", selection: $field.returnMethod) {
                Text("Walk").tag("walk"); Text("Reset").tag("reset")
            }.labelsHidden().frame(width: 92)
            Picker("", selection: $field.travel) {
                Text("Default").tag("default"); Text("Walk").tag("walk"); Text("Cannon").tag("cannon")
            }.labelsHidden().frame(width: 80)
            Spacer(minLength: 0)
            Button(action: remove) { Image(systemName: "minus.circle") }
                .buttonStyle(.plain).foregroundStyle(Theme.dust).help("Remove this field")
        }
        .frame(height: Theme.rowHeight + 4)
    }
}
