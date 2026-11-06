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

    func testExtraStepsRoundTrip() throws {
        var bug = ExtraStep(kind: "bug_run"); bug.bugs = ["werewolf", "king beetle"]; bug.everyMinutes = 45
        var pl = ExtraStep(kind: "planters"); pl.planterFields = ["rose", "", "clover"]; pl.planterTypes = ["petal", "paper", "candy"]; pl.harvestHours = 6
        let p = Profile(name: "t", fields: [FieldConfig(name: "rose")], extras: [bug, pl])
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("extras-\(UUID().uuidString).json")
        try p.save(to: url); defer { try? FileManager.default.removeItem(at: url) }
        let back = try Profile.load(url)
        XCTAssertEqual(back.extras.map(\.kind), ["bug_run", "planters"])
        XCTAssertEqual(back.extras[0].bugs, ["werewolf", "king beetle"])
        XCTAssertEqual(back.extras[0].everyMinutes, 45)
        XCTAssertEqual(back.extras[1].planterFields, ["rose", "", "clover"])
        XCTAssertEqual(back.extras[1].planterTypes, ["petal", "paper", "candy"])
        XCTAssertEqual(back.extras[1].harvestHours, 6)
    }
}

final class FieldColorsTests: XCTestCase {
    func testBlueHiveLikesBlueFieldsAndSkipsKnownRedOnes() {
        XCTAssertTrue(FieldColors.fits(field: "Bamboo", hive: "blue"))
        XCTAssertFalse(FieldColors.fits(field: "rose", hive: "blue"))
    }

    func testMixedHiveAndUnknownFieldsAlwaysFit() {
        XCTAssertTrue(FieldColors.fits(field: "rose", hive: "mixed"))
        XCTAssertTrue(FieldColors.fits(field: "cactus", hive: "red"))
    }

    func testRecommendedFollowsGameOrder() {
        XCTAssertEqual(FieldColors.recommended(for: "red"), ["mushroom", "strawberry", "rose", "pepper"])
        XCTAssertTrue(FieldColors.recommended(for: "mixed").isEmpty)
    }
}

final class RunOrderTests: XCTestCase {
    func testExtrasMoveBetweenFields() {
        var p = Profile(fields: [FieldConfig(name: "sunflower"), FieldConfig(name: "pine tree"), FieldConfig(name: "rose")],
                        extras: [ExtraStep(kind: "bug_run")])
        let bug = "e:" + p.extras[0].id.uuidString
        XCTAssertEqual(p.orderKeys.last, bug)               // default: after every field
        p.move(bug, before: "f:pine tree")
        XCTAssertEqual(p.orderKeys, ["f:sunflower", bug, "f:pine tree", "f:rose"])
        p.move("f:rose", before: "f:sunflower")
        XCTAssertEqual(p.fields.map(\.name), ["rose", "sunflower", "pine tree"])
        XCTAssertEqual(p.orderKeys, ["f:rose", "f:sunflower", bug, "f:pine tree"])
    }
}

final class PlanterTimerTests: XCTestCase {
    func testOnlyGrownSlotsAreReady() {
        var e = ExtraStep(kind: "planters")
        e.planterFields = ["rose", "pine tree", ""]; e.harvestHours = 4
        e.planterPlanted = [1000, 1000 + 3 * 3600, 1000]
        let now = 1000.0 + 4 * 3600
        XCTAssertEqual(e.planterRemaining(0, now: now), 0)
        XCTAssertEqual(e.planterRemaining(1, now: now), 3 * 3600)
        XCTAssertNil(e.planterRemaining(2, now: now))
        XCTAssertEqual(e.planterSlotsReady(now: now), [0])
    }
}
