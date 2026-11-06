import SwiftUI
import HiveMacCore

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
