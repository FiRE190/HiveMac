import SwiftUI

/// A pointy-top hexagon, the same one the app icon uses.
struct Hexagon: Shape {
    func path(in rect: CGRect) -> Path {
        let r = min(rect.width / 3.0.squareRoot(), rect.height / 2)       // radius that fits both ways
        let c = CGPoint(x: rect.midX, y: rect.midY)
        var p = Path()
        for i in 0..<6 {
            let a = CGFloat.pi / 3 * CGFloat(i) - CGFloat.pi / 2
            let pt = CGPoint(x: c.x + r * cos(a), y: c.y + r * sin(a))
            i == 0 ? p.move(to: pt) : p.addLine(to: pt)
        }
        p.closeSubpath()
        return p
    }
}

/// The mark in the header: three honeycomb cells, as in the app icon.
struct HiveMark: View {
    var size: CGFloat = 26
    var body: some View {
        let cell = size * 0.5
        ZStack {
            Hexagon().fill(Color(red: 1.00, green: 0.80, blue: 0.25)).frame(width: cell, height: cell).offset(x: -cell * 0.45, y: -cell * 0.38)
            Hexagon().fill(Color(red: 0.98, green: 0.62, blue: 0.14)).frame(width: cell, height: cell).offset(x: cell * 0.45, y: -cell * 0.38)
            Hexagon().fill(Color(red: 0.92, green: 0.48, blue: 0.10)).frame(width: cell, height: cell).offset(x: 0, y: cell * 0.42)
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

/// A small hexagon used as the status dot.
struct HexDot: View {
    var color: Color
    var size: CGFloat = 10
    var body: some View { Hexagon().fill(color).frame(width: size, height: size) }
}

/// The one memorable thing: a hexagon that fills with honey as the backpack fills. It shows the
/// number you actually watch while the macro runs.
struct HoneyGauge: View {
    var percent: Int?            // nil when the backpack cannot be read
    var active: Bool             // running: the fill is honey, otherwise it is muted
    var size: CGFloat = 116

    private var fraction: CGFloat { CGFloat(min(100, max(0, percent ?? 0))) / 100 }

    var body: some View {
        ZStack {
            Hexagon().fill(Theme.plank)
            // Honey rises from the bottom. The mask is the hexagon itself.
            GeometryReader { geo in
                Rectangle()
                    .fill(active ? Theme.honey : Theme.honey.opacity(0.45))
                    .frame(height: geo.size.height * fraction)
                    .frame(maxHeight: .infinity, alignment: .bottom)
                    .animation(.easeOut(duration: 0.5), value: fraction)
            }
            .mask(Hexagon())
            Hexagon().stroke(Theme.grain, lineWidth: 1.5)
            VStack(spacing: 0) {
                Text(percent.map { "\($0)" } ?? "none")
                    .font(Theme.serif(percent == nil ? 20 : 34, .semibold))
                    .foregroundStyle(fraction > 0.5 && percent != nil ? Theme.onHoney : Theme.wax)
                if percent != nil {
                    Text("percent").font(Theme.caption)
                        .foregroundStyle(fraction > 0.38 ? Theme.onHoney.opacity(0.8) : Theme.resin)
                }
            }
        }
        .frame(width: size, height: size)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Backpack")
        .accessibilityValue(percent.map { "\($0) percent" } ?? "not readable")
    }
}
