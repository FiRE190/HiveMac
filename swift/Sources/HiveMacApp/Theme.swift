import SwiftUI
import AppKit

/// The one place colours, type and spacing live. Nothing else in the app uses a raw hex value.
/// Direction: a beekeeper's shed. Warm graphite surfaces, one honey accent, the hexagon as the
/// shape language. Dark and light are both defined.
enum Theme {
    // MARK: Colour
    private static func ns(_ hex: UInt32) -> NSColor {
        NSColor(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
                blue: CGFloat(hex & 0xFF) / 255, alpha: 1)
    }

    private static func dynamic(dark: UInt32, light: UInt32) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? ns(dark) : ns(light)
        })
    }

    static let shed = dynamic(dark: 0x1A1815, light: 0xF3F1EC)      // window
    static let bench = dynamic(dark: 0x221F1B, light: 0xFFFFFF)     // content
    static let plank = dynamic(dark: 0x2C2823, light: 0xEBE7DF)     // raised controls
    static let grain = dynamic(dark: 0x3A352E, light: 0xD8D2C6)     // hairlines

    static let honey = Color(nsColor: ns(0xF2B134))                  // fills, same in both modes
    static let honeyText = dynamic(dark: 0xF2B134, light: 0x946200)  // accent text and icons, readable on light
    static let onHoney = Color(nsColor: ns(0x1A1300))                // text on a honey fill

    static let wax = dynamic(dark: 0xEFE9DC, light: 0x211D17)        // primary text
    static let resin = dynamic(dark: 0xB3AA99, light: 0x5E5648)      // secondary text
    static let dust = dynamic(dark: 0x857D6E, light: 0x7A7263)       // muted text

    static let leaf = dynamic(dark: 0x7DBB6A, light: 0x3F7D2C)       // ok
    static let ember = dynamic(dark: 0xE5604D, light: 0xBF3A28)      // problem

    // MARK: Spacing (4pt grid) and radius
    static let s1: CGFloat = 4, s2: CGFloat = 8, s3: CGFloat = 12, s4: CGFloat = 16, s6: CGFloat = 24
    static let rowHeight: CGFloat = 34
    static let controlRadius: CGFloat = 8
    static let panelRadius: CGFloat = 12

    // MARK: Type: New York (serif) for the name and the big readings, SF for everything else.
    static func serif(_ size: CGFloat, _ weight: Font.Weight = .semibold) -> Font { .system(size: size, weight: weight, design: .serif) }
    static let body = Font.system(size: 13)
    static let bodyStrong = Font.system(size: 13, weight: .medium)
    static let caption = Font.system(size: 12)
    static let figure = Font.system(size: 13, weight: .medium).monospacedDigit()
}
