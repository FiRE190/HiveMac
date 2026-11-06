import SwiftUI
import HiveMacCore

struct RowFrames: PreferenceKey {
    static var defaultValue: [String: CGRect] = [:]
    static func reduce(value: inout [String: CGRect], nextValue: () -> [String: CGRect]) { value.merge(nextValue()) { $1 } }
}

/// Drag to reorder. Nothing moves in the data until you let go, so the layout never shifts under
/// the pointer: the dragged row follows it and the rows it passes slide by its height.
final class Reorder: ObservableObject {
    @Published var dragging: String?
    @Published var dy: CGFloat = 0
    @Published var target = 0
    var frames: [String: CGRect] = [:]
    var snapshot: [String: CGRect] = [:]
    var order: [String] = []
    var from = 0
    var move: (String, String?) -> Void = { _, _ in }
    var keys: () -> [String] = { [] }

    private var height: CGFloat { dragging.flatMap { snapshot[$0]?.height } ?? 0 }

    func offset(for key: String) -> CGFloat {
        guard let d = dragging else { return 0 }
        if key == d { return dy }
        guard let r = order.firstIndex(of: key) else { return 0 }
        if r > from && r <= target { return -height }
        if r < from && r >= target { return height }
        return 0
    }

    func changed(_ key: String, dy: CGFloat) {
        if dragging == nil {
            order = keys(); snapshot = frames
            guard let i = order.firstIndex(of: key), snapshot[key] != nil else { return }
            from = i; target = i; dragging = key
        }
        guard dragging == key, let me = snapshot[key] else { return }
        self.dy = dy
        let centre = me.midY + dy
        let others = order.filter { $0 != key }
        let t = others.filter { (snapshot[$0]?.midY ?? 0) < centre }.count
        if t != target { withAnimation(.snappy(duration: 0.16)) { target = t } }
    }

    func ended() {
        guard let key = dragging else { return }
        let others = order.filter { $0 != key }
        let before = target < others.count ? others[target] : nil
        var t = Transaction(); t.disablesAnimations = true
        withTransaction(t) {
            move(key, before)
            dragging = nil; dy = 0
        }
    }
}

/// The grip at the left of every row. Drag it up or down to change the order.
struct DragHandle: View {
    let key: String
    @EnvironmentObject var reorder: Reorder
    var body: some View {
        Image(systemName: "line.3.horizontal")
            .font(.system(size: 12, weight: .semibold)).foregroundStyle(reorder.dragging == key ? Theme.honeyText : Theme.dust)
            .frame(width: 24, height: 28).contentShape(Rectangle())
            .gesture(DragGesture(minimumDistance: 2, coordinateSpace: .global)
                .onChanged { reorder.changed(key, dy: $0.translation.height) }
                .onEnded { _ in reorder.ended() })
            .help("Drag to change the order")
    }
}
