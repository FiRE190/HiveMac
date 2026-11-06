import XCTest
@testable import HiveMacCore

final class ProfileTests: XCTestCase {
    func testFieldReadsPythonKeysAndKeepsNatroDefaultsForTheRest() {
        let f = FieldConfig(json: ["name": "Rose", "minutes": 25, "backpack_percent": 80, "return_method": "reset", "enabled": false])
        XCTAssertEqual(f.name, "rose")
        XCTAssertEqual(f.minutes, 25); XCTAssertEqual(f.backpackPercent, 80)
        XCTAssertEqual(f.returnMethod, "reset"); XCTAssertFalse(f.enabled)
        XCTAssertEqual(f.pattern, "corner_x_snake"); XCTAssertEqual(f.camera, "right")     // Natro's rose defaults
        XCTAssertEqual(f.sprinklerLocation, "lower right")
    }

    func testFieldJSONRoundTrip() {
        var f = FieldConfig(name: "pepper"); f.minutes = 7.5; f.invertLR = true; f.shiftLock = true
        let back = FieldConfig(json: f.json)
        XCTAssertEqual(back, f)
    }

    func testProfileSaveLoadAndTheRealPythonDefaultProfile() throws {
        let tmp = FileManager.default.temporaryDirectory.appendingPathComponent("p-\(UUID().uuidString).json")
        defer { try? FileManager.default.removeItem(at: tmp) }
        var p = Profile(name: "night", fields: [FieldConfig(name: "clover"), FieldConfig(name: "stump")], notes: "n")
        p.fields[1].enabled = false
        try p.save(to: tmp)
        XCTAssertEqual(try Profile.load(tmp), p)
        let real = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("profiles/default_profile.json")
        let d = try Profile.load(real)
        XCTAssertEqual(d.fields.first?.name, "sunflower")
        XCTAssertEqual(d.fields.first?.returnMethod, "walk")
    }

    func testEmptyProfileFallsBackToOneField() throws {
        let tmp = FileManager.default.temporaryDirectory.appendingPathComponent("e-\(UUID().uuidString).json")
        defer { try? FileManager.default.removeItem(at: tmp) }
        try Data(#"{"name":"x","fields":[]}"#.utf8).write(to: tmp)
        XCTAssertEqual(try Profile.load(tmp).fields.map(\.name), ["sunflower"])
    }

    func testHiveProfileRoundTripThroughTheStore() {
        let store = ConfigStore(defaults: ["hive": ["color": "mixed", "bee_count": 50, "avg_bee_level": 10, "cub_buddy": false, "backpack_percent": 90]], url: nil)
        var h = HiveProfile(store: store)
        XCTAssertEqual(h.beeCount, 50); XCTAssertFalse(h.cubBuddy)
        h.color = "blue"; h.cubBuddy = true; h.beeCount = 42; h.write(to: store)
        XCTAssertEqual(HiveProfile(store: store), h)
    }
}
