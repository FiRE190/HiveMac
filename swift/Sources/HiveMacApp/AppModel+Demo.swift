import SwiftUI
import HiveMacCore
import HiveMacPlatform

extension AppModel {
    /// Made-up numbers for pictures and for trying the layout. Nothing here reads the game or the
    /// real settings; run it with HIVEMAC_HOME pointing at a scratch folder.
    var isDemo: Bool { ProcessInfo.processInfo.environment["HIVEMAC_DEMO"] != nil }

    func applyDemo() {
        state = .gathering; detail = "sunflower corner_x_snake m w4"
        running = true; runtimeSeconds = 2538; backpack = 72; currentField = "sunflower"
        var s = LoopStats(); s.cycles = 14; s.converts = 13; s.deaths = 1; stats = s
        permissions = PermissionStatus(screenRecording: true, accessibility: true)
        live = LiveReadings(windowFound: true, windowText: "Roblox found, 1440 by 900", backpack: 70,
                            backpackRGB: "rgb(146, 126, 78)", healthGrey: false, hivePrompt: true, calibrated: true)
        var f2 = FieldConfig(name: "pine tree"); f2.minutes = 12; f2.backpackPercent = 90
        var f3 = FieldConfig(name: "bamboo"); f3.returnMethod = "reset"
        var f4 = FieldConfig(name: "stump"); f4.enabled = false
        runs = [RunEntry(file: "demo.json", name: "Strawberry grinder"), RunEntry(file: "d2.json", name: "Clover fast")]; activeRunFile = "demo.json"
        profile = Profile(name: "Strawberry grinder", fields: [FieldConfig(name: "sunflower"), f2, f3, f4],
                          extras: [ExtraStep(kind: "bug_run"), ExtraStep(kind: "planters")])
        hive.color = "blue"; hive.cubBuddy = true
        ["Resetting: attempt 1", "Converting: done", "Traveling: sunflower", "Gathering: sunflower corner_x_snake m w4 until 95% or 10 min",
         "Traveling: hive", "Converting: done"].forEach(append)
    }
}
