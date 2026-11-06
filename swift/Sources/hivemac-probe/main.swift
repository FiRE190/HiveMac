import Foundation
import HiveMacCore
import HiveMacPlatform

// hivemac-probe: proves the native layer works on this Mac and measures what it costs.
// Reads only; it never sends keys or mouse input.
//   swift run hivemac-probe [x y]     pixel position in points, default 100 100

let args = CommandLine.arguments
let x = args.count > 2 ? Int(args[1]) ?? 100 : 100
let y = args.count > 2 ? Int(args[2]) ?? 100 : 100

let perm = Permissions.current()
print("Screen Recording: \(perm.screenRecording ? "granted" : "NOT granted")")
print("Accessibility:    \(perm.accessibility ? "granted" : "NOT granted")")

if let w = WindowFinder.robloxWindow() {
    print("Roblox window:    \(w.width)x\(w.height) at \(w.left),\(w.top)")
} else {
    print("Roblox window:    not found (open Roblox in a window to see it here)")
}

let screen = ScreenCapture()
guard perm.screenRecording else { print("Cannot capture without Screen Recording."); exit(1) }

var times: [Double] = []
var last: (r: Int, g: Int, b: Int)?
for _ in 0..<20 {
    last = screen.pixel(x: x, y: y)
    times.append(screen.lastCaptureSeconds)
}
if let c = last { print(String(format: "Pixel at %d,%d:  rgb(%d, %d, %d)", x, y, c.r, c.g, c.b)) } else { print("Pixel at \(x),\(y): could not read") }
let sorted = times.sorted()
print(String(format: "1 pixel capture:  median %.1f ms, max %.1f ms (20 reads)", sorted[10] * 1000, sorted[19] * 1000))

var big: [Double] = []
var img: RGBImage?
for _ in 0..<10 {
    img = screen.grab(WindowBounds(left: x, top: y, width: 400, height: 120))
    big.append(screen.lastCaptureSeconds)
}
if let img { print(String(format: "400x120 region:    %dx%d pixels, median %.1f ms", img.width, img.height, big.sorted()[5] * 1000)) }

// Compare with the older, lighter CoreGraphics route (deprecated in macOS 14, still present).
import CoreGraphics
func legacyGrab(_ x: Int, _ y: Int, _ w: Int, _ h: Int) -> CGImage? {
    CGDisplayCreateImage(CGMainDisplayID(), rect: CGRect(x: x, y: y, width: w, height: h))
}
var legacy: [Double] = []
var got = false
for _ in 0..<20 {
    let t0 = ProcessInfo.processInfo.systemUptime
    if legacyGrab(x, y, 1, 1) != nil { got = true }
    legacy.append(ProcessInfo.processInfo.systemUptime - t0)
}
print(got ? String(format: "legacy CGDisplayCreateImage 1 pixel: median %.2f ms", legacy.sorted()[10] * 1000)
          : "legacy CGDisplayCreateImage: returned nothing on this macOS")
