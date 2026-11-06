import XCTest
@testable import HiveMacCore

final class RecorderTests: XCTestCase {
    private func ev(_ t: Double, _ k: String, _ d: Bool) -> KeyEvent { KeyEvent(t: t, key: k, down: d) }

    func testWalkHoldBecomesTilesAtWalkSpeed() {
        // 1 s at speed 28 = 28 studs = 7 tiles
        let s = Recorder.steps(from: [ev(0, "w", true), ev(1, "w", false)], walkSpeed: 28)
        XCTAssertEqual(s.count, 1)
        XCTAssertEqual(s[0].type, "walk"); XCTAssertEqual(s[0].keys, ["w"]); XCTAssertEqual(s[0].tiles, 7, accuracy: 0.001)
    }

    func testDiagonalKeysHeldTogetherAreOneWalkInKeyOrder() {
        let s = Recorder.steps(from: [ev(0, "d", true), ev(0.1, "w", true), ev(1.1, "w", false), ev(1.1, "d", false)], walkSpeed: 28)
        XCTAssertTrue(s.contains { $0.type == "walk" && $0.keys == ["w", "d"] })
    }

    func testRotationsMergeAndGapsBecomeWaits() {
        let s = Recorder.steps(from: [ev(0, ".", true), ev(0.05, ".", false), ev(0.1, ".", true), ev(0.15, ".", false),
                                      ev(1.5, "space", true), ev(1.55, "space", false)], walkSpeed: 28)
        XCTAssertEqual(s.map(\.type), ["rotate", "wait", "tap"])
        XCTAssertEqual(s[0].count, 2); XCTAssertEqual(s[0].direction, "right")
    }

    func testUnknownKeysAreIgnoredAndSaveRoundTrips() throws {
        let steps = Recorder.steps(from: [ev(0, "q", true), ev(0.1, "q", false), ev(0.2, "w", true), ev(0.7, "w", false)], walkSpeed: 28)
        XCTAssertEqual(steps.count, 1)
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("rec-\(UUID().uuidString).json")
        defer { try? FileManager.default.removeItem(at: url) }
        try PathFile(name: "t", steps: steps).save(to: url)
        XCTAssertEqual(try PathFile.load(url).steps, steps)
    }

    func testCropClipsToTheImage() {
        let img = RGBImage(width: 4, height: 3, pixels: (0..<36).map { UInt8($0) })
        let c = img.cropped(x: 2, y: 1, width: 5, height: 5)!
        XCTAssertEqual(c.width, 2); XCTAssertEqual(c.height, 2)
        XCTAssertEqual(c.pixel(0, 0).r, 18)           // row 1, column 2 starts at byte (1*4+2)*3
        XCTAssertNil(img.cropped(x: 9, y: 9, width: 2, height: 2))
    }
}
