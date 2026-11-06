import SwiftUI
import HiveMacCore
import HiveMacPlatform

struct CalibrateView: View {
    @EnvironmentObject var model: AppModel
    @State private var advanced = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                if !model.permissions.allGranted {
                    Text("Screen Recording or Accessibility is off. Turn them on with the gear at the top right.")
                        .font(Theme.caption).foregroundStyle(Theme.ember).padding(.top, Theme.s4)
                }

                SectionTitle("Roblox")
                HStack(spacing: Theme.s3) {
                    HexDot(color: model.live.windowFound ? Theme.leaf : Theme.ember)
                    Text(model.live.windowText).font(Theme.body).foregroundStyle(Theme.wax)
                    Spacer()
                    Button("Detect Roblox") { model.detectRoblox() }.buttonStyle(HoneyButtonStyle())
                }
                .frame(minHeight: Theme.rowHeight)
                Text("Open Roblox, stand in your hive, press Detect. That is all most people need.")
                    .font(Theme.caption).foregroundStyle(Theme.dust).fixedSize(horizontal: false, vertical: true)

                if model.live.calibrated {
                    HStack(spacing: Theme.s4) {
                        Text("Backpack").font(Theme.body).foregroundStyle(Theme.resin)
                        Text(model.live.backpack.map { "\($0) percent" } ?? "not readable").font(Theme.figure).foregroundStyle(Theme.wax)
                        Text("Gather a little by hand: it should follow the bar.").font(Theme.caption).foregroundStyle(Theme.dust)
                        Spacer()
                    }
                    .padding(.top, Theme.s3)
                }

                Button { withAnimation(.snappy(duration: 0.15)) { advanced.toggle() } } label: {
                    HStack(spacing: Theme.s1) {
                        Image(systemName: advanced ? "chevron.down" : "chevron.right").font(.system(size: 9, weight: .bold)).frame(width: 10)
                        Text("Advanced").font(Theme.body)
                    }.foregroundStyle(Theme.resin)
                }
                .buttonStyle(.plain).padding(.top, Theme.s6)
                if advanced {
                    RecordWalkSection()
                    PicturesSection()
                }
            }
            .padding(.horizontal, Theme.s6).padding(.bottom, Theme.s6)
        }
        .onAppear { model.refreshLive() }
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
            if !ok { Button("Open") { Permissions.openSettings(pane) }.buttonStyle(QuietButtonStyle()) }
        }
        .frame(minHeight: Theme.rowHeight + 8)
    }
}


struct RecordWalkSection: View {
    @EnvironmentObject var model: AppModel
    @State private var kind = "to_field"
    @State private var field = "sunflower"

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionTitle("Record a walk")
            Text("Only if Natro's walk is wrong for you. Your walk replaces it for that field.").font(Theme.caption).foregroundStyle(Theme.dust)
                .padding(.bottom, Theme.s2)
            HStack(spacing: Theme.s2) {
                Choice(options: [("to_field", "To the field"), ("to_hive", "Back to the hive")], selection: $kind, width: 140).disabled(model.recording)
                Choice(options: FieldDefaults.order.map { ($0, $0.capitalized) }, selection: $field, width: 140).disabled(model.recording)
                if model.recording {
                    Button("Stop") { model.toggleRecording(kind: kind, field: field) }.buttonStyle(QuietButtonStyle(tint: Theme.ember))
                } else {
                    Button("Record") { model.toggleRecording(kind: kind, field: field) }.buttonStyle(HoneyButtonStyle())
                }
                Button("Remove mine") { model.removeUserWalk(kind: kind, field: field) }.buttonStyle(QuietButtonStyle()).disabled(model.recording)
            }
            if let m = model.calibMessage { Text(m).font(Theme.caption).foregroundStyle(Theme.resin).padding(.top, Theme.s2).fixedSize(horizontal: false, vertical: true) }
        }
    }
}

struct PicturesSection: View {
    @EnvironmentObject var model: AppModel
    @State private var sheet: PictureKind?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionTitle("Pictures")
            Text("Pictures HiveMac looks for on screen. Stand where the picture is visible, then pick it out.").font(Theme.caption).foregroundStyle(Theme.dust)
                .padding(.bottom, Theme.s2)
            HStack(spacing: Theme.s2) {
                ForEach(PictureKind.allCases) { k in
                    Button(k.title) { sheet = k }.buttonStyle(QuietButtonStyle())
                }
            }
        }
        .sheet(item: $sheet) { PictureSheet(kind: $0) }
    }
}

enum PictureKind: String, CaseIterable, Identifiable {
    case hivePrompt = "hive_prompt", hiveView = "hive_view", cannonPrompt = "cannon_prompt"
    var id: String { rawValue }
    var title: String {
        switch self { case .hivePrompt: "Hive prompt"; case .hiveView: "Hive view"; case .cannonPrompt: "Cannon prompt" }
    }
    var help: String {
        switch self {
        case .hivePrompt: "Stand at your hive until the Make Honey prompt shows, then drag a box around the prompt."
        case .hiveView: "Face the hive from the ramp and drag a box around something that only shows there, like the hive's front."
        case .cannonPrompt: "Stand on the cannon button until its prompt shows, then drag a box around it."
        }
    }
}

/// Takes a picture of the Roblox window and lets you drag a box around the part to save.
struct PictureSheet: View {
    var kind: PictureKind
    @EnvironmentObject var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var snapshot: RGBImage?
    @State private var image: NSImage?
    @State private var drag: (CGPoint, CGPoint)?

    private let shown: CGFloat = 560

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.s3) {
            Text(kind.title).font(Theme.serif(18, .semibold)).foregroundStyle(Theme.wax)
            Text(kind.help).font(Theme.caption).foregroundStyle(Theme.resin)
            if let image, let snapshot {
                let scale = shown / CGFloat(snapshot.width)
                Image(nsImage: image).resizable().frame(width: shown, height: CGFloat(snapshot.height) * scale)
                    .overlay {
                        if let d = drag {
                            Rectangle().stroke(Theme.honey, lineWidth: 2)
                                .frame(width: abs(d.1.x - d.0.x), height: abs(d.1.y - d.0.y))
                                .position(x: (d.0.x + d.1.x) / 2, y: (d.0.y + d.1.y) / 2)
                        }
                    }
                    .gesture(DragGesture(minimumDistance: 2).onChanged { v in drag = (v.startLocation, v.location) })
                    .clipped()
                HStack {
                    Button("Take a new picture") { take() }.buttonStyle(QuietButtonStyle())
                    Spacer()
                    Button("Cancel") { dismiss() }.buttonStyle(QuietButtonStyle())
                    Button("Save") {
                        guard let d = drag else { return }
                        let x = min(d.0.x, d.1.x) / scale, y = min(d.0.y, d.1.y) / scale
                        model.saveTemplate(key: kind.rawValue, from: snapshot, x: Int(x), y: Int(y),
                                           w: Int(abs(d.1.x - d.0.x) / scale), h: Int(abs(d.1.y - d.0.y) / scale))
                        dismiss()
                    }.buttonStyle(HoneyButtonStyle()).disabled(drag == nil)
                }
            } else {
                Text("Roblox was not found. Open it, then try again.").font(Theme.body).foregroundStyle(Theme.ember)
                HStack { Spacer(); Button("Close") { dismiss() }.buttonStyle(QuietButtonStyle()) }
            }
        }
        .padding(Theme.s6).frame(width: shown + 2 * Theme.s6).background(Theme.shed).tint(Theme.honey)
        .onAppear { take() }
    }

    private func take() {
        drag = nil
        guard let s = model.snapshotRoblox() else { snapshot = nil; image = nil; return }
        snapshot = s
        let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: s.width, pixelsHigh: s.height, bitsPerSample: 8, samplesPerPixel: 3,
                                   hasAlpha: false, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: s.width * 3, bitsPerPixel: 24)!
        s.pixels.withUnsafeBufferPointer { rep.bitmapData!.update(from: $0.baseAddress!, count: s.pixels.count) }
        let img = NSImage(size: NSSize(width: s.width, height: s.height)); img.addRepresentation(rep)
        image = img
    }
}
