import SwiftUI
import HiveMacCore

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
                    let left = step.planterRemaining(i, now: Date().timeIntervalSince1970)
                    Text(left == nil ? "Empty" : left == 0 ? "Ready" : "Ready in " + MobTimers.describeDuration(left ?? 0))
                        .font(Theme.caption).foregroundStyle(left == 0 ? Theme.leaf : Theme.dust)
                    Spacer(minLength: 0)
                    Button("Planted now") { step.planterPlanted[i] = Date().timeIntervalSince1970 }
                        .buttonStyle(QuietButtonStyle()).disabled(step.planterFields[i].isEmpty)
                        .help("Start this slot's timer, for a planter you just put down")
                }
            }
            Toggle("Replant after every harvest", isOn: $step.planterReplant).toggleStyle(.checkbox).font(Theme.body)
            HStack(spacing: Theme.s2) {
                Text("Grows for").font(Theme.caption).foregroundStyle(Theme.dust)
                TextField("", value: $step.harvestHours, format: .number).fieldStyle(width: 56)
                Text("hours").font(Theme.caption).foregroundStyle(Theme.dust)
            }
        }
    }
}
