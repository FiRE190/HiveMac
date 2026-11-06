import XCTest
@testable import HiveMacCore

/// The repo's JSON data directory, found relative to this file so the tests read the same
/// route files the Python app does.
private let pathsDir: URL = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    .deletingLastPathComponent().appendingPathComponent("config/paths/natro")

final class StepsTests: XCTestCase {
    func testGotoRampMatchesNatro() {
        let slot1 = Paths.gotoRampSteps(hiveSlot: 1)
        XCTAssertEqual(slot1[0], .walk(["w"], tiles: 5))
        XCTAssertEqual(slot1[1].keys, ["d"])
        XCTAssertEqual(slot1[1].tiles, 5.2, accuracy: 1e-9)
        XCTAssertEqual(Paths.gotoRampSteps(hiveSlot: 6).last?.tiles ?? 0, 51.2, accuracy: 1e-9)
        XCTAssertEqual(Paths.gotoRampSteps(hiveSlot: 99).count, 2)   // clamped to slot 6
        let expanded = Paths.expand([Step(type: "gotoramp"), .tap("e")], hiveSlot: 2)
        XCTAssertEqual(expanded.map(\.type), ["walk", "walk", "tap"])
    }

    func testPatternKeyBinding() {
        XCTAssertEqual(Paths.bindPatternKeys()["tc_fb"], "w")
        XCTAssertEqual(Paths.bindPatternKeys(invertFB: true)["tc_fb"], "s")
        XCTAssertEqual(Paths.bindPatternKeys(invertLR: true)["afc_lr"], "a")
    }

    func testHoldScalingOnlyTouchesMovementHolds() {
        let steps: [Step] = [.hold(["w"], seconds: 2.8), .hold(["space"], seconds: 0.2), .walk(["w"], tiles: 3)]
        let scaled = Paths.scaleHolds(steps, recordedSpeed: 28, actualSpeed: 14)
        XCTAssertEqual(scaled[0].seconds, 5.6, accuracy: 1e-9)
        XCTAssertEqual(scaled[1].seconds, 0.2)
        XCTAssertEqual(scaled[2].tiles, 3)
        XCTAssertEqual(Paths.keyDuration(1, referenceSpeed: 28, actualSpeed: 0), 1)
    }

    func testTotalSecondsAndSlug() {
        XCTAssertEqual(Paths.totalSeconds([.walk(["w"], tiles: 7), .wait(1.5), .tap("e", count: 5)], speed: 28),
                       7 * 4.0 / 28 + 1.5 + 0.3, accuracy: 1e-9)
        XCTAssertEqual(Paths.fieldSlug("  Blue Flower!! "), "blue_flower")
        XCTAssertEqual(Paths.fieldSlug("Pine-Tree"), "pine_tree")
    }

    func testJSONRoundTripOmitsDefaults() throws {
        let data = try JSONEncoder().encode(Step.walk(["w", "d"], tiles: 9))
        let obj = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        XCTAssertEqual(Set(obj.keys), ["type", "keys", "tiles"])
        XCTAssertEqual(try JSONDecoder().decode(Step.self, from: data), .walk(["w", "d"], tiles: 9))
    }

    /// Every converted Natro route decodes: 17 walk back routes and the field routes.
    func testAllRealRouteFilesDecode() throws {
        let toHive = try FileManager.default.contentsOfDirectory(at: pathsDir.appendingPathComponent("to_hive"),
                                                                 includingPropertiesForKeys: nil)
            .filter { $0.pathExtension == "json" }
        XCTAssertEqual(toHive.count, 17)
        let toField = try FileManager.default.contentsOfDirectory(at: pathsDir.appendingPathComponent("to_field"),
                                                                  includingPropertiesForKeys: nil)
            .filter { $0.pathExtension == "json" }
        XCTAssertGreaterThanOrEqual(toField.count, 29)
        for url in toHive + toField {
            let pf = try PathFile.load(url)
            XCTAssertFalse(pf.steps.isEmpty, url.lastPathComponent)
            for s in pf.steps { XCTAssertFalse(s.keys.contains { $0.hasPrefix("sc_") }, url.lastPathComponent) }
        }
    }

    func testSunflowerWalkBackMatchesNatro() throws {
        let pf = try PathFile.load(pathsDir.appendingPathComponent("to_hive/sunflower.json"))
        XCTAssertEqual(pf.walkSpeed, 28)
        XCTAssertEqual(pf.steps.count, 9)
        XCTAssertEqual(pf.steps[1], .walk(["d"], tiles: 13.5))
        XCTAssertEqual(pf.steps[2], .walk(["w"], tiles: 45))
    }
}
