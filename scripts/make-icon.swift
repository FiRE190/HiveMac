import AppKit

// Draws the HiveMac app icon (three honeycomb cells) into an .iconset folder.
// Usage: swift scripts/make-icon.swift <output.iconset>

let outDir = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "HiveMac.iconset"
try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)

func hexagon(center: CGPoint, radius: CGFloat) -> NSBezierPath {
    let path = NSBezierPath()
    for i in 0..<6 {
        let angle = CGFloat.pi / 3 * CGFloat(i) + CGFloat.pi / 6
        let point = CGPoint(x: center.x + radius * cos(angle), y: center.y + radius * sin(angle))
        i == 0 ? path.move(to: point) : path.line(to: point)
    }
    path.close()
    return path
}

func png(pixels: Int) -> Data {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels,
                               bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                               colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    let s = CGFloat(pixels)

    let background = NSBezierPath(roundedRect: NSRect(x: s * 0.06, y: s * 0.06, width: s * 0.88, height: s * 0.88),
                                  xRadius: s * 0.2, yRadius: s * 0.2)
    NSGradient(colors: [NSColor(calibratedRed: 0.12, green: 0.09, blue: 0.05, alpha: 1),
                        NSColor(calibratedRed: 0.36, green: 0.22, blue: 0.06, alpha: 1)])!
        .draw(in: background, angle: -90)

    // Three touching honeycomb cells, bright amber to deep gold.
    let r = s * 0.17
    let dx = r * sqrt(3)
    let cx = s * 0.5, cy = s * 0.5
    let cells: [(CGPoint, NSColor)] = [
        (CGPoint(x: cx - dx / 2, y: cy + r * 0.78), NSColor(calibratedRed: 1.00, green: 0.80, blue: 0.25, alpha: 1)),
        (CGPoint(x: cx + dx / 2, y: cy + r * 0.78), NSColor(calibratedRed: 0.98, green: 0.62, blue: 0.14, alpha: 1)),
        (CGPoint(x: cx, y: cy - r * 0.78), NSColor(calibratedRed: 0.92, green: 0.48, blue: 0.10, alpha: 1)),
    ]
    for (center, color) in cells {
        let cell = hexagon(center: center, radius: r * 0.93)
        color.setFill()
        cell.fill()
        NSColor.white.withAlphaComponent(0.25).setStroke()
        cell.lineWidth = max(1, s * 0.006)
        cell.stroke()
    }

    NSGraphicsContext.restoreGraphicsState()
    return rep.representation(using: .png, properties: [:])!
}

let files: [(String, Int)] = [
    ("icon_16x16", 16), ("icon_16x16@2x", 32),
    ("icon_32x32", 32), ("icon_32x32@2x", 64),
    ("icon_128x128", 128), ("icon_128x128@2x", 256),
    ("icon_256x256", 256), ("icon_256x256@2x", 512),
    ("icon_512x512", 512), ("icon_512x512@2x", 1024),
]
for (name, pixels) in files {
    try png(pixels: pixels).write(to: URL(fileURLWithPath: "\(outDir)/\(name).png"))
}
