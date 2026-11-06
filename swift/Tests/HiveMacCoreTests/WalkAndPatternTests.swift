import XCTest
@testable import HiveMacCore

final class FakeClock: Clock {
    var t = 0.0
    var onSleep: ((FakeClock) -> Void)?
    func now() -> Double { t }
    func sleep(_ s: Double) { t += s; onSleep?(self) }
}

final class FakeActuator: Actuator {
    var events: [String] = []
    var down = Set<String>()
    var mouse = false
    var onTap: ((String) -> Void)?
    var onKeyDown: ((String) -> Void)?
    func keyDown(_ k: String) { down.insert(k); events.append("down \(k)"); onKeyDown?(k) }
    func keyUp(_ k: String) { down.remove(k); events.append("up \(k)") }
    func tap(_ k: String, holdS: Double) { events.append("tap \(k)"); onTap?(k) }
    func mouseDown() { mouse = true; events.append("mouse down") }
    func mouseUp() { mouse = false; events.append("mouse up") }
    func moveMouse(_ x: Int, _ y: Int) { events.append("move \(x) \(y)") }
    func releaseAll() { down.removeAll(); mouse = false; events.append("release") }
    func taps(_ key: String) -> Int { events.filter { $0 == "tap \(key)" }.count }
}

final class WalkAndPatternTests: XCTestCase {
    func testSpeedModelTilesToSeconds() {
        XCTAssertEqual(SpeedModel(baseSpeed: 28).secondsForTiles(9), 36.0 / 28, accuracy: 1e-9)
        XCTAssertEqual(SpeedModel(baseSpeed: 28, multiplier: { 2 }).secondsForTiles(9), 18.0 / 28, accuracy: 1e-9)
        XCTAssertEqual(Paths.keyDuration(1, referenceSpeed: 28, actualSpeed: 56), 0.5, accuracy: 1e-9)
    }

    func testWalkerHoldsForTheRightTimeAndReleases() {
        let act = FakeActuator(), clock = FakeClock()
        let w = Walker(actuator: act, speed: SpeedModel(baseSpeed: 28), clock: clock)
        let held = w.walk(["w", "d"], tiles: 7)
        XCTAssertEqual(held, 1.0, accuracy: 0.06)
        XCTAssertEqual(Array(act.events.prefix(2)), ["down w", "down d"])
        XCTAssertEqual(Array(act.events.suffix(2)), ["up w", "up d"])
        XCTAssertTrue(act.down.isEmpty)
    }

    func testWalkerStopsEarlyAndStillReleasesKeys() throws {
        let act = FakeActuator(), clock = FakeClock(), stop = Signal()
        let w = Walker(actuator: act, speed: SpeedModel(baseSpeed: 28), clock: clock, stop: stop, slice: 0.1)
        clock.onSleep = { c in if c.t >= 0.3 { stop.set() } }
        let held = w.walk(["w"], tiles: 70)          // would take 10 s
        XCTAssertLessThan(held, 0.5)
        XCTAssertTrue(act.down.isEmpty)
        XCTAssertFalse(try w.run([.walk(["w"], tiles: 1)]))
    }

    func testWalkerPauseReleasesAndResumes() {
        let act = FakeActuator(), clock = FakeClock(), pause = Signal(true)
        let w = Walker(actuator: act, speed: SpeedModel(baseSpeed: 28), clock: clock, pause: pause, slice: 0.1)
        var calls = 0
        clock.onSleep = { _ in calls += 1; if calls >= 3 { pause.clear() } }
        w.hold(["w"], 0.2)
        XCTAssertTrue(act.events.dropLast().contains("up w"))
        XCTAssertEqual(act.events.filter { $0 == "down w" }.count, 2)
        XCTAssertTrue(act.down.isEmpty)
    }

    func testRunStepsMapsAbstractKeysAndHandlesEveryType() throws {
        let act = FakeActuator(), clock = FakeClock()
        let w = Walker(actuator: act, speed: SpeedModel(baseSpeed: 28), clock: clock)
        var mouseDown = Step(type: "mouse"); mouseDown.direction = "down"
        var mouseUp = Step(type: "mouse"); mouseUp.direction = "up"
        var zoom = Step(type: "zoom"); zoom.direction = "out"; zoom.count = 3
        let steps: [Step] = [.walk(["tc_lr"], tiles: 1), .rotate("right", count: 2), .tap("e"), .wait(0.1),
                             zoom, mouseDown, .hold(["w"], seconds: 0.1), mouseUp]
        XCTAssertTrue(try w.run(steps, keymap: Paths.bindPatternKeys(invertLR: true)))
        XCTAssertTrue(act.events.contains("down d"))
        XCTAssertEqual(act.events.filter { $0 == "tap ." }.count, 2)
        XCTAssertEqual(act.events.filter { $0 == "tap o" }.count, 3)
        XCTAssertTrue(act.events.contains("tap e") && act.events.contains("mouse down"))
        XCTAssertThrowsError(try w.run([Step(type: "bogus")]))
    }

    func testEveryPatternBuildsFiniteStepsWithAbstractKeys() throws {
        for name in Patterns.names {
            for size in ["xs", "s", "m", "l", "xl"] {
                let steps = try Patterns.build(name, size: size, width: 3, facingCorner: 1)
                XCTAssertFalse(steps.isEmpty, name)
                for s in steps {
                    XCTAssertTrue(["walk", "wait"].contains(s.type))
                    if s.type == "walk" {
                        XCTAssertGreaterThan(s.tiles, 0, "\(name) \(size)")
                        XCTAssertTrue(s.keys.allSatisfy { Patterns.abstractKeys.contains($0) || $0 == "w" }, name)
                    }
                }
            }
        }
        XCTAssertThrowsError(try Patterns.build("nope"))
    }

    func testCornerXSnakeMatchesNatroShape() throws {
        let walks = try Patterns.build("corner_x_snake", size: "m", width: 4).filter { $0.type == "walk" }
        XCTAssertEqual(walks.count, 24)
        XCTAssertEqual(walks[0].keys, ["tc_lr"]); XCTAssertEqual(walks[0].tiles, 4.0)
        XCTAssertTrue(walks.contains { $0.keys == ["afc_lr"] && $0.tiles == 10.0 })
    }

    func testFieldDefaultsCoverAllFieldsWithKnownPatterns() {
        XCTAssertEqual(Set(FieldDefaults.order), Set(FieldDefaults.table.keys))
        XCTAssertEqual(FieldDefaults.order.count, 17)
        for (field, d) in FieldDefaults.table {
            XCTAssertNotNil(Patterns.all[d.pattern], field)
            XCTAssertNotNil(Patterns.sizeFactors[d.size], field)
            XCTAssertTrue(["none", "left", "right"].contains(d.camera), field)
            XCTAssertNotNil(Sprinkler.fieldDimensions[field], field)
        }
    }

    func testSprinklerStartLocationAndPlacement() {
        let steps = Sprinkler.startLocationSteps(field: "sunflower", location: "upper left", distance: 8, speed: 18)
        XCTAssertEqual(steps.map(\.keys), [["w"], ["a"]])
        XCTAssertEqual(steps[0].seconds, 1.25 * 8 / 10, accuracy: 1e-9)          // 1250 ms * 0.8 at speed 18
        XCTAssertEqual(Sprinkler.startLocationSteps(field: "clover", location: "center", distance: 1, speed: 28).map(\.type), ["wait"])
        XCTAssertTrue(Sprinkler.placementSteps(type: "none", location: "center", slotKey: "1", speed: 28).isEmpty)
        XCTAssertEqual(Sprinkler.placementSteps(type: "supreme", location: "center", slotKey: "3", speed: 28), [.tap("3")])
        let diamond = Sprinkler.placementSteps(type: "diamond", location: "upper left", slotKey: "1", speed: 28)
        XCTAssertEqual(diamond.filter { $0.type == "tap" }.count, 4)
    }
}
