import XCTest
@testable import HiveMacCore

final class MobTimersTests: XCTestCase {
    func testReadyUntilKilledThenWaitsForRespawn() {
        var t = MobTimers()
        XCTAssertTrue(t.isReady("ladybug", now: 1000))
        t.markDone("ladybug", at: 1000)
        XCTAssertFalse(t.isReady("ladybug", now: 1100))
        XCTAssertEqual(t.remaining("ladybug", now: 1100), 230, accuracy: 0.001)
        XCTAssertTrue(t.isReady("ladybug", now: 1330))
    }

    func testEachMobHasItsOwnTimer() {
        var t = MobTimers()
        t.markDone("ladybug", at: 0); t.markDone("werewolf", at: 0)
        XCTAssertEqual(t.due(["ladybug", "werewolf", "spider"], now: 400), ["ladybug", "spider"])
        XCTAssertEqual(t.due(["werewolf"], now: 3630), ["werewolf"])
    }

    func testMobWithoutTimerIsAlwaysReady() {
        var t = MobTimers()
        t.markDone("black bear", at: 0)
        XCTAssertTrue(t.isReady("black bear", now: 1))
    }

    func testSurvivesRestart() throws {
        var t = MobTimers(); t.markDone("king beetle", at: 5000)
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("mt-\(UUID().uuidString).json")
        t.save(to: url); defer { try? FileManager.default.removeItem(at: url) }
        XCTAssertEqual(MobTimers.load(url), t)
        XCTAssertFalse(MobTimers.load(url).isReady("king beetle", now: 6000))
    }

    func testDescribe() {
        XCTAssertEqual(MobTimers.describe(remaining: 0, timed: true), "ready")
        XCTAssertEqual(MobTimers.describe(remaining: 61, timed: true), "back in 2 min")
        XCTAssertEqual(MobTimers.describe(remaining: 7200, timed: true), "back in 2.0 h")
        XCTAssertEqual(MobTimers.describe(remaining: 0, timed: false), "no timer")
    }
}
