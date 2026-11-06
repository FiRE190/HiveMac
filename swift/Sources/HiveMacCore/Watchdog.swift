import Foundation

/// Stops a run that has gone quiet. The loop beats on every status change and backpack read;
/// if nothing beats for `timeout` seconds while running (not paused), the run is stalled.
public struct Watchdog: Equatable, Sendable {
    public var timeout: TimeInterval
    public private(set) var lastBeat: TimeInterval

    public init(timeout: TimeInterval = 90, now: TimeInterval) { self.timeout = timeout; self.lastBeat = now }

    public mutating func beat(at now: TimeInterval) { lastBeat = now }

    public func isStalled(now: TimeInterval, running: Bool, paused: Bool) -> Bool {
        running && !paused && now - lastBeat > timeout
    }
}
