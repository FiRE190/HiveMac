import Foundation

/// macOS virtual key codes (ANSI layout) by the names the macro and path files use.
public enum KeyCodes {
    public static let byName: [String: UInt16] = {
        var m: [String: UInt16] = [
            "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9, "b": 11, "q": 12,
            "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23,
            "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34,
            "p": 35, "enter": 36, "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44,
            "n": 45, "m": 46, ".": 47, "tab": 48, "space": 49, "`": 50, "delete": 51, "esc": 53,
            "cmd": 55, "shift": 56, "alt": 58, "ctrl": 59,
            "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98, "f8": 100, "f9": 101,
            "f10": 109, "f11": 103, "f12": 111, "left": 123, "right": 124, "down": 125, "up": 126,
        ]
        m["escape"] = 53; m["return"] = 36
        return m
    }()

    public static func code(for name: String) -> UInt16? { byName[name.lowercased()] }

    /// Preferred display name for a key code ("f9", "esc"), nil for keys we do not know.
    public static func name(for code: UInt16) -> String? {
        let preferred = byName.filter { $0.key != "escape" && $0.key != "return" }
        return preferred.first { $0.value == code }?.key
    }

    /// Keys the macro itself presses. A stop key on one of these would stop the macro by itself.
    public static let usedByMacro: Set<String> = [
        "1", "2", "3", "4", "5", "6", "7", "w", "a", "s", "d", ",", ".", "i", "o", "space", "e", "shift", "r", "esc", "enter",
    ]

    public enum StopKeyError: Error, Equatable {
        case unknown, usedByMacro(String)
        public var message: String {
            switch self {
            case .unknown: return "That key is not supported."
            case .usedByMacro(let k): return "\(k.uppercased()) is a key the macro presses, so it would stop itself. Pick another."
            }
        }
    }

    /// Validates a stop key name, returning its code.
    public static func validateStopKey(_ name: String) -> Result<UInt16, StopKeyError> {
        let n = name.lowercased()
        guard let c = code(for: n) else { return .failure(.unknown) }
        if usedByMacro.contains(n) { return .failure(.usedByMacro(n)) }
        return .success(c)
    }
}
