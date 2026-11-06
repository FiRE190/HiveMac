import Foundation

/// Pure HUD decoding. No screen access here, only numbers, so all of it is unit tested.
/// Colours are RGB.
public enum Hud {
    /// The backpack bar is read from one pixel and decoded by colour into 5 percent steps.
    /// This is Natro Macro's ladder (submacros/background.ahk nm_backpackPercent).
    /// Returns nil when the colour is not a bar colour; an empty bar reads nil too and the
    /// filter counts that as 0.
    public static func backpackPercent(r: Int, g: Int, b: Int) -> Int? {
        let col = (r << 16) | (g << 8) | b
        let red = col & 0xFF0000
        let gb = col & 0x00FFFF
        if red <= 0x690000 {
            if red <= 0x4B0000 {
                if red <= 0x420000 {
                    if red <= 0x410000 && gb <= 0x00FF80 && gb > 0x00FF86 { return 0 }
                    if red > 0x410000 && gb <= 0x00FF80 && gb > 0x00FC85 { return 5 }
                    return nil
                }
                if red <= 0x470000 {
                    if red <= 0x440000 && gb <= 0x00FE85 && gb > 0x00F984 { return 10 }
                    if red > 0x440000 && gb <= 0x00FB84 && gb > 0x00F582 { return 15 }
                    return nil
                }
                if gb <= 0x00F782 && gb > 0x00F080 { return 20 }
                return nil
            }
            if red <= 0x5B0000 {
                if red <= 0x4F0000 && gb <= 0x00F280 && gb > 0x00EA7D { return 25 }
                if red <= 0x550000 && gb <= 0x00EC7D && gb > 0x00E37A { return 30 }
                if red > 0x550000 && gb <= 0x00E57A && gb > 0x00DA76 { return 35 }
                return nil
            }
            if red <= 0x620000 && gb <= 0x00DC76 && gb > 0x00D072 { return 40 }
            if red > 0x620000 && gb <= 0x00D272 && gb > 0x00C66D { return 45 }
            return nil
        }
        if red <= 0x9C0000 {
            if red <= 0x850000 {
                if red <= 0x7B0000 {
                    if red <= 0x720000 && gb <= 0x00C86D && gb > 0x00BA68 { return 50 }
                    if red > 0x720000 && gb <= 0x00BC68 && gb > 0x00AD62 { return 55 }
                    return nil
                }
                if gb <= 0x00AF62 && gb > 0x009E5C { return 60 }
                return nil
            }
            if red <= 0x900000 && gb <= 0x00A05C && gb > 0x008F55 { return 65 }
            if red > 0x900000 && gb <= 0x009155 && gb > 0x007E4E { return 70 }
            return nil
        }
        if red <= 0xC40000 {
            if red <= 0xA90000 && gb <= 0x00804E && gb > 0x006C46 { return 75 }
            if red <= 0xB60000 && gb <= 0x006E46 && gb > 0x005A3F { return 80 }
            if red > 0xB60000 && gb <= 0x005D3F && gb > 0x004637 { return 85 }
            return nil
        }
        if red <= 0xD30000 && gb <= 0x004A37 && gb > 0x00322E { return 90 }
        if col == 0xF70017 || (red >= 0xE00000 && gb <= 0x002427 && gb > 0x001000) { return 100 }
        if gb <= 0x00342E { return 95 }
        return nil
    }

    /// Natro's health bar check: dead when all three channels sit in the grey band.
    public static func isGrey(r: Int, g: Int, b: Int, low: Int = 0x4D, high: Int = 0x83) -> Bool {
        [r, g, b].allSatisfy { (low...high).contains($0) }
    }
}

/// Rolling mean of the last N readings, like Natro's 6 sample filter at 1 Hz. A nil sample
/// (no bar colour at the pixel) counts as 0 and extends `unreadableStreak`, so the loop can
/// tell a long run of "nothing there" from a real empty bar.
public struct BackpackFilter: Sendable {
    private var values: [Int] = []
    private let size: Int
    public private(set) var unreadableStreak = 0

    public init(size: Int = 6) { self.size = size }

    @discardableResult
    public mutating func push(_ value: Int?) -> Int {
        if let v = value { unreadableStreak = 0; append(v) }
        else { unreadableStreak += 1; append(0) }
        return self.value
    }

    private mutating func append(_ v: Int) {
        values.append(v)
        if values.count > size { values.removeFirst() }
    }

    public var value: Int {
        guard !values.isEmpty else { return 0 }
        // Python's round() is half to even; keep the same rounding so both apps agree.
        return Int((Double(values.reduce(0, +)) / Double(values.count)).rounded(.toNearestOrEven))
    }

    public mutating func reset() { values.removeAll(); unreadableStreak = 0 }
}
