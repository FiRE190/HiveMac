import XCTest
@testable import HiveMacCore

final class WatchdogTests: XCTestCase {
    func testStallsOnlyAfterTimeoutWithoutBeats() {
        var w = Watchdog(timeout: 90, now: 0)
        XCTAssertFalse(w.isStalled(now: 90, running: true, paused: false))
        XCTAssertTrue(w.isStalled(now: 91, running: true, paused: false))
        w.beat(at: 91)
        XCTAssertFalse(w.isStalled(now: 150, running: true, paused: false))
    }

    func testPausedOrStoppedIsNeverStalled() {
        let w = Watchdog(timeout: 10, now: 0)
        XCTAssertFalse(w.isStalled(now: 999, running: true, paused: true))
        XCTAssertFalse(w.isStalled(now: 999, running: false, paused: false))
    }
}
