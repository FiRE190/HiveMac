import XCTest
@testable import HiveMacCore

final class HudTests: XCTestCase {
    func testKnownPoints() {
        XCTAssertEqual(Hud.backpackPercent(r: 0xF7, g: 0x00, b: 0x17), 100)
        XCTAssertNil(Hud.backpackPercent(r: 0x75, g: 0x75, b: 0x75))   // unlit bar background
        XCTAssertNil(Hud.backpackPercent(r: 0, g: 0, b: 0))
    }

    /// Same band table as the Python test (red low excl, red high incl, gb low excl, gb high incl, percent).
    func testBandsInOrder() {
        let bands: [(Int, Int, Int, Int, Int)] = [
            (0x41, 0x42, 0xFC85, 0xFF80, 5), (0x42, 0x44, 0xF984, 0xFE85, 10),
            (0x44, 0x47, 0xF582, 0xFB84, 15), (0x47, 0x4B, 0xF080, 0xF782, 20),
            (0x4B, 0x4F, 0xEA7D, 0xF280, 25), (0x4F, 0x55, 0xE37A, 0xEC7D, 30),
            (0x55, 0x5B, 0xDA76, 0xE57A, 35), (0x5B, 0x62, 0xD072, 0xDC76, 40),
            (0x62, 0x69, 0xC66D, 0xD272, 45), (0x69, 0x72, 0xBA68, 0xC86D, 50),
            (0x72, 0x7B, 0xAD62, 0xBC68, 55), (0x7B, 0x85, 0x9E5C, 0xAF62, 60),
            (0x85, 0x90, 0x8F55, 0xA05C, 65), (0x90, 0x9C, 0x7E4E, 0x9155, 70),
            (0x9C, 0xA9, 0x6C46, 0x804E, 75), (0xA9, 0xB6, 0x5A3F, 0x6E46, 80),
            (0xB6, 0xC4, 0x4637, 0x5D3F, 85), (0xC4, 0xD3, 0x322E, 0x4A37, 90),
            (0xD3, 0xDF, 0x2000, 0x342E, 95), (0xE0, 0xFF, 0x1000, 0x2427, 100),
        ]
        var last = -1
        for (rLo, rHi, gbLo, gbHi, expected) in bands {
            let r = (rLo + 1 + rHi) / 2, gb = (gbLo + 1 + gbHi) / 2
            let got = Hud.backpackPercent(r: r, g: gb >> 8, b: gb & 0xFF)
            XCTAssertEqual(got, expected, String(format: "r=%02X gb=%04X", r, gb))
            XCTAssertGreaterThan(got ?? -1, last)
            last = got ?? last
        }
    }

    func testFilterAveragesAndCountsUnreadable() {
        var f = BackpackFilter(size: 3)
        XCTAssertEqual(f.push(nil), 0); XCTAssertEqual(f.unreadableStreak, 1)
        XCTAssertEqual(f.push(90), 45); XCTAssertEqual(f.unreadableStreak, 0)   // the nil counted as 0
        XCTAssertEqual(f.push(100), 63)
        f.push(100); f.push(100)
        XCTAssertEqual(f.value, 100)
        f.reset()
        XCTAssertEqual(f.value, 0)
    }

    func testGreyBand() {
        XCTAssertTrue(Hud.isGrey(r: 0x4D, g: 0x4D, b: 0x4D))
        XCTAssertTrue(Hud.isGrey(r: 0x83, g: 0x83, b: 0x83))
        XCTAssertFalse(Hud.isGrey(r: 0x4C, g: 0x60, b: 0x60))
        XCTAssertFalse(Hud.isGrey(r: 0xF0, g: 0x20, b: 0x20))
    }
}
