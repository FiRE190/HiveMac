import Foundation

/// Which flower colour a field is known for, for suggesting fields to a hive. Community wiki data
/// (the Bee Swarm Simulator fandom wiki and guides, checked 2026-11-05), so it can be off: sources
/// disagree on some fields and flowers vary between servers. A field with no clear colour is not
/// listed here, and it counts as a fit for any hive. This never changes how the macro runs.
public enum FieldColors {
    public static let table: [String: String] = [
        "blue flower": "blue", "stump": "blue", "bamboo": "blue", "pine tree": "blue",
        "mushroom": "red", "strawberry": "red", "rose": "red", "pepper": "red",
        "spider": "white", "sunflower": "white", "dandelion": "white",
    ]

    /// True when the field suits a hive of this colour. Mixed hives and unknown fields always fit.
    public static func fits(field: String, hive: String) -> Bool {
        guard hive != "mixed", let c = table[field.lowercased()] else { return true }
        return c == hive
    }

    /// Only the fields that are known to match, for a "good for your bees" hint.
    public static func recommended(for hive: String) -> [String] {
        hive == "mixed" ? [] : FieldDefaults.order.filter { table[$0] == hive }
    }
}
