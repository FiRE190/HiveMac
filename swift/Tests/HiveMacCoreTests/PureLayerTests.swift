import XCTest
@testable import HiveMacCore

final class PureLayerTests: XCTestCase {
    let win = WindowBounds(left: 100, top: 50, width: 1600, height: 900)

    func testRelPointRoundTrip() {
        let p = RelPoint.from(x: 900, y: 500, in: win)
        let a = p.absolute(in: win)
        XCTAssertEqual(a.x, 900); XCTAssertEqual(a.y, 500)
        let moved = WindowBounds(left: 0, top: 0, width: 800, height: 450)   // a smaller window: same spot, scaled
        XCTAssertEqual(p.absolute(in: moved).x, 400)
    }

    func testRegionAndClamp() {
        let r = RelRegion(fx: 0.25, fy: 0.5, fw: 0.5, fh: 0.25).absolute(in: win)
        XCTAssertEqual(r, WindowBounds(left: 500, top: 500, width: 800, height: 225))
        let outside = Layout.clamp(WindowBounds(left: 50, top: 0, width: 5000, height: 5000), to: win)
        XCTAssertEqual(outside, win)
    }

    func testNatroDefaultsMatchPythonValues() {
        let w = WindowBounds(left: 0, top: 0, width: 1600, height: 900)
        let d = Layout.natroDefaults(w, offsetY: 0)
        XCTAssertEqual(d.backpackPixel.fx, (800.0 + 62) / 1600, accuracy: 1e-12)
        XCTAssertEqual(d.healthPixel.fx, (1600.0 - 75) / 1600, accuracy: 1e-12)
        XCTAssertEqual(d.hivePromptRegion.fw, 400.0 / 1600, accuracy: 1e-12)
    }

    func testContentRectAndWindowPicking() {
        XCTAssertEqual(Layout.contentRect(win, mode: "windowed", titleBar: 28),
                       WindowBounds(left: 100, top: 78, width: 1600, height: 872))
        XCTAssertEqual(Layout.contentRect(win, mode: "fullscreen", titleBar: 28), win)
        XCTAssertEqual(Layout.contentRect(win, mode: "windowed", titleBar: 9999).height, 900 - 225)   // capped at a quarter
        let infos = [Layout.WindowInfo(owner: "Finder", layer: 0, bounds: win),
                     Layout.WindowInfo(owner: "Roblox", layer: 25, bounds: win),
                     Layout.WindowInfo(owner: "RobloxPlayer", layer: 0, bounds: WindowBounds(left: 1, top: 2, width: 800, height: 600)),
                     Layout.WindowInfo(owner: "RobloxPlayer", layer: 0, bounds: WindowBounds(left: 3, top: 4, width: 50, height: 50))]
        XCTAssertEqual(Layout.pickWindow(infos), WindowBounds(left: 1, top: 2, width: 800, height: 600))
        XCTAssertNil(Layout.pickWindow([]))
    }

    func testTemplateSearch() {
        var img = RGBImage(width: 20, height: 12, fill: (10, 10, 10))
        var tpl = RGBImage(width: 3, height: 2, fill: (200, 30, 30))
        tpl.set(1, 1, (30, 200, 30))
        for y in 0..<2 { for x in 0..<3 { img.set(7 + x, 4 + y, (UInt8(tpl.pixel(x, y).r), UInt8(tpl.pixel(x, y).g), UInt8(tpl.pixel(x, y).b))) } }
        let hit = ImageSearch.find(img, template: tpl, tolerance: 4)
        XCTAssertEqual(hit?.x, 7); XCTAssertEqual(hit?.y, 4)
        var off = img; off.set(8, 5, (60, 60, 60))                      // one pixel way off: no match
        XCTAssertNil(ImageSearch.find(off, template: tpl, tolerance: 4))
        // The centre and corners are always checked, so sampling every other pixel still rejects it,
        // and still finds the real match.
        XCTAssertNil(ImageSearch.find(off, template: tpl, tolerance: 4, step: 2))
        XCTAssertEqual(ImageSearch.find(img, template: tpl, tolerance: 4, step: 2)?.x, 7)
        XCTAssertNil(ImageSearch.find(RGBImage(width: 2, height: 2, fill: (0, 0, 0)), template: tpl))   // template larger than image
    }

    func testHLSCounting() {
        var img = RGBImage(width: 4, height: 4, fill: (0, 0, 0))
        for x in 0..<4 { img.set(x, 0, (255, 0, 0)) }
        for x in 0..<2 { img.set(x, 1, (250, 5, 5)) }
        XCTAssertEqual(ImageSearch.countHLS(img, low: (0, 40, 90), high: (10, 60, 100)), 6)
        let white = RGBImage(width: 2, height: 2, fill: (255, 255, 255))
        XCTAssertEqual(ImageSearch.countHLS(white, low: (0, 95, 0), high: (360, 100, 100)), 4)
    }

    func testKeyCodesAndStopKeyRules() {
        XCTAssertEqual(KeyCodes.code(for: "F9"), 101)
        XCTAssertEqual(KeyCodes.code(for: "space"), 49)
        XCTAssertEqual(KeyCodes.name(for: 101), "f9")
        XCTAssertEqual(KeyCodes.name(for: 53), "esc")
        XCTAssertEqual(KeyCodes.validateStopKey("f9"), .success(101))
        XCTAssertEqual(KeyCodes.validateStopKey("w"), .failure(.usedByMacro("w")))
        XCTAssertEqual(KeyCodes.validateStopKey("Space"), .failure(.usedByMacro("space")))
        XCTAssertEqual(KeyCodes.validateStopKey("nope"), .failure(.unknown))
        XCTAssertTrue(KeyCodes.StopKeyError.usedByMacro("e").message.contains("E is a key"))
        for k in ["1", "2", "3", "4", "5", "6", "7", ",", ".", "i", "o"] {
            XCTAssertNotNil(KeyCodes.validateStopKey(k).failureValue, k)
        }
    }

    func testAppDirsAndPathLookupPrefersUserFiles() throws {
        let tmp = FileManager.default.temporaryDirectory.appendingPathComponent("hivemac-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: tmp) }
        let dirs = AppDirs.standard(environment: ["HIVEMAC_HOME": tmp.path])
        XCTAssertEqual(dirs.data.path, tmp.path)
        XCTAssertTrue(AppDirs.standard(environment: [:], home: URL(fileURLWithPath: "/Users/x")).data.path
            .hasSuffix("Library/Application Support/HiveMac"))
        try dirs.ensure()
        let builtIn = tmp.appendingPathComponent("builtin")
        try FileManager.default.createDirectory(at: builtIn.appendingPathComponent("to_hive"), withIntermediateDirectories: true)
        try Data("{}".utf8).write(to: builtIn.appendingPathComponent("to_hive/blue_flower.json"))
        XCTAssertEqual(dirs.findPath(kind: "to_hive", field: "Blue Flower", builtIn: builtIn)?.deletingLastPathComponent().deletingLastPathComponent().lastPathComponent, "builtin")
        try Data("{}".utf8).write(to: dirs.userPaths.appendingPathComponent("to_hive/blue_flower.json"))
        XCTAssertEqual(dirs.findPath(kind: "to_hive", field: "Blue Flower", builtIn: builtIn)?.path.contains("/user/"), true)
        XCTAssertNil(dirs.findPath(kind: "to_hive", field: "nowhere", builtIn: builtIn))
    }

    func testConfigStoreMergesDefaultsKeepsUnknownKeysAndReadsGameSettings() throws {
        let tmp = FileManager.default.temporaryDirectory.appendingPathComponent("cfg-\(UUID().uuidString).json")
        defer { try? FileManager.default.removeItem(at: tmp) }
        let defaults: [String: Any] = ["game": ["walk_speed": 28, "hive_slot": 1, "mouse_park": [0.25, 0.2]], "app": ["emergency_stop_key": "f9"]]
        try Data(#"{"game": {"hive_slot": 3}, "extra": {"keep": true}}"#.utf8).write(to: tmp)
        let store = ConfigStore(defaults: defaults, url: tmp)
        XCTAssertEqual(store.int("game.hive_slot"), 3)               // file wins
        XCTAssertEqual(store.double("game.walk_speed"), 28)          // default fills the gap
        XCTAssertEqual(store.string("app.emergency_stop_key"), "f9")
        store.set("game.walk_speed", 33.5); store.set("app.new.deep", "x")
        try store.save()
        let reloaded = ConfigStore(defaults: defaults, url: tmp)
        XCTAssertEqual(reloaded.double("game.walk_speed"), 33.5)
        XCTAssertEqual(reloaded.string("app.new.deep"), "x")
        XCTAssertEqual(reloaded.bool("extra.keep"), true)            // unknown keys survive
        let g = reloaded.gameSettings()
        XCTAssertEqual(g.walkSpeed, 33.5); XCTAssertEqual(g.hiveSlot, 3); XCTAssertEqual(g.mousePark.x, 0.25)
    }

    func testRealDefaultConfigFileDecodes() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("config/default_config.json")
        let store = try ConfigStore(defaultsURL: url, url: nil)
        XCTAssertEqual(store.gameSettings().walkSpeed, 28)
        XCTAssertEqual(store.string("app.emergency_stop_key"), "f9")
        XCTAssertEqual(store.int("hive.bee_count"), 50)
        XCTAssertEqual(store.bool("hive.cub_buddy"), false)
    }
}

private extension Result {
    var failureValue: Failure? { if case .failure(let f) = self { return f } else { return nil } }
}
