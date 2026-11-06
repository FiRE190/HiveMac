import Foundation

/// Walk from the field arrival point to a start corner and place sprinklers (Natro's
/// nm_setSprinkler). Distances are Natro's millisecond holds at walk speed 18, expressed as
/// `hold` steps scaled to the player's speed.
public enum Sprinkler {
    /// [length, width] in Natro milliseconds at distance 10 and speed 18.
    public static let fieldDimensions: [String: (length: Double, width: Double)] = [
        "sunflower": (1250, 2000), "dandelion": (2500, 1000), "mushroom": (1250, 1750),
        "blue flower": (2750, 750), "clover": (2000, 1500), "spider": (2000, 2000),
        "strawberry": (1500, 2000), "bamboo": (3000, 1250), "pineapple": (1750, 3000),
        "stump": (1500, 1500), "cactus": (1500, 2500), "pumpkin": (1500, 2500),
        "pine tree": (2500, 1750), "rose": (2500, 1500), "mountain top": (2250, 1500),
        "pepper": (1500, 2250), "coconut": (1500, 2250),
    ]
    public static let types = ["none", "basic", "silver", "golden", "diamond", "supreme"]
    static let natroSpeed = 18.0

    private static func msHold(_ keys: [String], _ ms: Double, _ speed: Double) -> Step {
        .hold(keys, seconds: ms / 1000 * natroSpeed / max(1, speed))
    }

    /// Move from the arrival point to the chosen start location ("upper left", "center", ...).
    public static func startLocationSteps(field: String, location: String, distance: Int, speed: Double) -> [Step] {
        let loc = location.lowercased()
        guard let dims = fieldDimensions[field.lowercased()], loc != "center" else {
            return loc == "center" ? [.wait(1)] : []
        }
        let flen = dims.length * Double(distance) / 10, fwid = dims.width * Double(distance) / 10
        var out: [Step] = []
        if loc.contains("upper") || loc.contains("top") { out.append(msHold(["w"], flen, speed)) }
        else if loc.contains("lower") || loc.contains("bottom") { out.append(msHold(["s"], flen, speed)) }
        if loc.contains("left") { out.append(msHold(["a"], fwid, speed)) }
        else if loc.contains("right") { out.append(msHold(["d"], fwid, speed)) }
        return out
    }

    /// Key sequence that drops the sprinklers for a type. Basic and supreme are one press;
    /// the multi sprinkler types jump and place at offsets like Natro.
    public static func placementSteps(type: String, location: String, slotKey: String, speed: Double) -> [Step] {
        let t = type.lowercased()
        if t == "none" { return [] }
        if t == "supreme" || t == "basic" { return [.tap(slotKey)] }
        let loc = location.lowercased()
        let fbBack = loc.contains("upper") ? "s" : "w"
        let fbFwd = loc.contains("upper") ? "w" : "s"
        let lrIn = loc.contains("left") ? "d" : "a"
        let side = loc.contains("left") ? "a" : "d"
        func jumpPlace() -> [Step] { [.hold(["space"], seconds: 0.2), .tap(slotKey), .wait(0.5)] }

        var out = jumpPlace()
        if ["silver", "golden", "diamond"].contains(t) { out += [msHold([fbBack], 1000, speed), .wait(0.5)] + jumpPlace() }
        if t == "silver" { out += [msHold([fbFwd], 1000, speed)] }
        if ["golden", "diamond"].contains(t) { out += [msHold([lrIn], 1000, speed), .wait(0.5)] + jumpPlace() }
        if t == "golden" { out += [msHold([fbFwd, side], 1400, speed)] }
        if t == "diamond" {
            out += [msHold([fbFwd], 1000, speed), .wait(0.5)] + jumpPlace()
            out += [msHold([side], 1000, speed)]
        }
        return out
    }
}
