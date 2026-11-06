import Foundation

/// A small RGB image, row major, 3 bytes per pixel.
public struct RGBImage: Equatable, Sendable {
    public let width: Int, height: Int
    public var pixels: [UInt8]

    public init(width: Int, height: Int, pixels: [UInt8]) {
        precondition(pixels.count == width * height * 3)
        self.width = width; self.height = height; self.pixels = pixels
    }

    public init(width: Int, height: Int, fill: (r: UInt8, g: UInt8, b: UInt8)) {
        self.init(width: width, height: height,
                  pixels: (0..<(width * height)).flatMap { _ in [fill.r, fill.g, fill.b] })
    }

    public func pixel(_ x: Int, _ y: Int) -> (r: Int, g: Int, b: Int) {
        let i = (y * width + x) * 3
        return (Int(pixels[i]), Int(pixels[i + 1]), Int(pixels[i + 2]))
    }

    public mutating func set(_ x: Int, _ y: Int, _ c: (r: UInt8, g: UInt8, b: UInt8)) {
        let i = (y * width + x) * 3
        pixels[i] = c.r; pixels[i + 1] = c.g; pixels[i + 2] = c.b
    }
}

public enum ImageSearch {
    /// Top left of the first place where every sampled template pixel is within `tolerance`
    /// per channel (Natro's Gdip_ImageSearch "variation"). Meant for small templates in small
    /// regions. `step` samples every n-th template pixel.
    public static func find(_ image: RGBImage, template: RGBImage, tolerance: Int = 10, step: Int = 1) -> (x: Int, y: Int)? {
        let th = template.height, tw = template.width
        guard th > 0, tw > 0, th <= image.height, tw <= image.width else { return nil }
        // Corners and centre first: they eliminate most candidates early.
        var order: [(Int, Int)] = [(0, 0), (th - 1, tw - 1), (th / 2, tw / 2), (0, tw - 1), (th - 1, 0)]
        let seen = Set(order.map { $0.0 * 100_000 + $0.1 })
        for y in stride(from: 0, to: th, by: max(1, step)) {
            for x in stride(from: 0, to: tw, by: max(1, step)) where !seen.contains(y * 100_000 + x) { order.append((y, x)) }
        }
        for oy in 0...(image.height - th) {
            for ox in 0...(image.width - tw) {
                var ok = true
                for (ty, tx) in order {
                    let a = image.pixel(ox + tx, oy + ty), b = template.pixel(tx, ty)
                    if abs(a.r - b.r) > tolerance || abs(a.g - b.g) > tolerance || abs(a.b - b.b) > tolerance { ok = false; break }
                }
                if ok { return (ox, oy) }
            }
        }
        return nil
    }

    /// RGB (0 to 255) to HLS with H in 0..360, L and S in 0..100.
    public static func hls(r: Int, g: Int, b: Int) -> (h: Double, l: Double, s: Double) {
        let rf = Double(r) / 255, gf = Double(g) / 255, bf = Double(b) / 255
        let mx = max(rf, gf, bf), mn = min(rf, gf, bf)
        let light = (mx + mn) / 2, delta = mx - mn
        guard delta > 1e-6 else { return (0, light * 100, 0) }
        let sat = delta / (light <= 0.5 ? mx + mn : 2 - mx - mn)
        let rc = (mx - rf) / delta, gc = (mx - gf) / delta, bc = (mx - bf) / delta
        var hue = mx == rf ? bc - gc : (mx == gf ? 2 + rc - bc : 4 + gc - rc)
        hue = (hue / 6).truncatingRemainder(dividingBy: 1)
        if hue < 0 { hue += 1 }
        return (hue * 360, light * 100, sat * 100)
    }

    /// Pixels whose HLS falls inside [low, high].
    public static func countHLS(_ image: RGBImage, low: (h: Double, l: Double, s: Double), high: (h: Double, l: Double, s: Double)) -> Int {
        var n = 0
        for y in 0..<image.height {
            for x in 0..<image.width {
                let p = image.pixel(x, y)
                let c = hls(r: p.r, g: p.g, b: p.b)
                if c.h >= low.h && c.h <= high.h && c.l >= low.l && c.l <= high.l && c.s >= low.s && c.s <= high.s { n += 1 }
            }
        }
        return n
    }
}
