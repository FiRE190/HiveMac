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

/// A step in a run besides a field. Saved with the run; the engine does not run these yet.
public struct ExtraStep: Equatable, Identifiable, Sendable {
    public static let bugs = ["ladybug", "rhino beetle", "spider", "mantis", "scorpion", "werewolf",
                              "coconut crab", "king beetle", "black bear"]
    public var id = UUID()
    public var kind: String                 // bug_run, planters
    public var enabled = true
    public var everyMinutes = 30.0          // bug run: how often. planters: not used (see harvestHours)
    public var bugs: [String] = ["ladybug", "rhino beetle"]
    public var planterFields: [String] = ["", "", ""]
    public var planterTypes: [String] = ["paper", "paper", "paper"]
    /// Natro's 12 planters.
    public static let planters = ["paper", "ticking", "plastic", "candy", "red clay", "blue clay", "tacky",
                                  "pesticide", "heat-treated", "hydroponic", "petal", "planter of plenty"]
    public var harvestHours = 4.0

    public init(kind: String) { self.kind = kind }

    public init(json d: [String: Any]) {
        self.init(kind: (d["kind"] as? String) ?? "bug_run")
        if let v = (d["enabled"] as? NSNumber)?.boolValue { enabled = v }
        if let v = (d["every_minutes"] as? NSNumber)?.doubleValue { everyMinutes = v }
        if let v = d["bugs"] as? [String] { bugs = v }
        if let v = d["planter_fields"] as? [String] { planterFields = (v + ["", "", ""]).prefix(3).map { $0 } }
        if let v = d["planter_types"] as? [String] { planterTypes = (v + ["paper", "paper", "paper"]).prefix(3).map { $0 } }
        if let v = (d["harvest_hours"] as? NSNumber)?.doubleValue { harvestHours = v }
    }

    public var json: [String: Any] {
        ["kind": kind, "enabled": enabled, "every_minutes": everyMinutes, "bugs": bugs,
         "planter_fields": planterFields, "planter_types": planterTypes, "harvest_hours": harvestHours]
    }
}

/// A named list of fields to farm, stored as `profiles/<name>.json` like the Python app.
public struct Profile: Equatable {
    public var name: String
    public var fields: [FieldConfig]
    public var notes: String
    public var extras: [ExtraStep]

    public init(name: String = "default", fields: [FieldConfig] = [FieldConfig(name: "sunflower")], notes: String = "", extras: [ExtraStep] = []) {
        self.name = name; self.fields = fields; self.notes = notes; self.extras = extras
    }

    public static func load(_ url: URL) throws -> Profile {
        let obj = (try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any]) ?? [:]
        let fields = ((obj["fields"] as? [[String: Any]]) ?? []).map(FieldConfig.init(json:))
        return Profile(name: (obj["name"] as? String) ?? url.deletingPathExtension().lastPathComponent,
                       fields: fields.isEmpty ? [FieldConfig(name: "sunflower")] : fields,
                       notes: (obj["notes"] as? String) ?? "",
                       extras: ((obj["extras"] as? [[String: Any]]) ?? []).map(ExtraStep.init(json:)))
    }

    public func save(to url: URL) throws {
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        let obj: [String: Any] = ["name": name, "fields": fields.map(\.json), "notes": notes, "extras": extras.map(\.json)]
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
