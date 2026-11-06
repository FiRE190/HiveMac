import Foundation

extension FieldConfig {
    /// Reads a field from the profile JSON (Python's key names). Anything missing keeps Natro's
    /// default for that field.
    public init(json d: [String: Any]) {
        self.init(name: (d["name"] as? String) ?? "sunflower")
        func str(_ k: String) -> String? { d[k] as? String }
        func num(_ k: String) -> Double? { (d[k] as? NSNumber)?.doubleValue }
        func flag(_ k: String) -> Bool? { (d[k] as? NSNumber)?.boolValue }
        if let v = str("pattern") { pattern = v }
        if let v = str("size") { size = v }
        if let v = num("width") { width = Int(v) }
        if let v = flag("invert_fb") { invertFB = v }
        if let v = flag("invert_lr") { invertLR = v }
        if let v = str("camera") { camera = v }
        if let v = num("turns") { turns = Int(v) }
        if let v = num("minutes") { minutes = v }
        if let v = num("backpack_percent") { backpackPercent = Int(v) }
        if let v = str("sprinkler_location") { sprinklerLocation = v }
        if let v = num("sprinkler_distance") { sprinklerDistance = Int(v) }
        if let v = flag("shift_lock") { shiftLock = v }
        if let v = str("travel") { travel = v }
        if let v = str("return_method") { returnMethod = v }
        if let v = flag("enabled") { enabled = v }
    }

    public var json: [String: Any] {
        ["name": name, "pattern": pattern, "size": size, "width": width, "invert_fb": invertFB,
         "invert_lr": invertLR, "camera": camera, "turns": turns, "minutes": minutes,
         "backpack_percent": backpackPercent, "sprinkler_location": sprinklerLocation,
         "sprinkler_distance": sprinklerDistance, "shift_lock": shiftLock, "travel": travel,
         "return_method": returnMethod, "enabled": enabled]
    }
}

/// A named list of fields to farm, stored as `profiles/<name>.json` like the Python app.
public struct Profile: Equatable {
    public var name: String
    public var fields: [FieldConfig]
    public var notes: String

    public init(name: String = "default", fields: [FieldConfig] = [FieldConfig(name: "sunflower")], notes: String = "") {
        self.name = name; self.fields = fields; self.notes = notes
    }

    public static func load(_ url: URL) throws -> Profile {
        let obj = (try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any]) ?? [:]
        let fields = ((obj["fields"] as? [[String: Any]]) ?? []).map(FieldConfig.init(json:))
        return Profile(name: (obj["name"] as? String) ?? url.deletingPathExtension().lastPathComponent,
                       fields: fields.isEmpty ? [FieldConfig(name: "sunflower")] : fields,
                       notes: (obj["notes"] as? String) ?? "")
    }

    public func save(to url: URL) throws {
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        let obj: [String: Any] = ["name": name, "fields": fields.map(\.json), "notes": notes]
        try JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted, .sortedKeys]).write(to: url, options: .atomic)
    }
}

/// The hive profile from the settings: used to suggest fields and set the default backpack target.
public struct HiveProfile: Equatable {
    public var color = "mixed"          // blue, red, white, mixed
    public var beeCount = 50
    public var avgBeeLevel = 10
    public var cubBuddy = false
    public var backpackPercent = 90

    public init() {}

    public init(store: ConfigStore) {
        color = store.string("hive.color", "mixed")
        beeCount = store.int("hive.bee_count", 50)
        avgBeeLevel = store.int("hive.avg_bee_level", 10)
        cubBuddy = store.bool("hive.cub_buddy", false)
        backpackPercent = store.int("hive.backpack_percent", 90)
    }

    public func write(to store: ConfigStore) {
        store.set("hive.color", color); store.set("hive.bee_count", beeCount)
        store.set("hive.avg_bee_level", avgBeeLevel); store.set("hive.cub_buddy", cubBuddy)
        store.set("hive.backpack_percent", backpackPercent)
    }
}
