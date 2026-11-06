import Foundation

/// Where things live. The same folder as the Python app when run from the app bundle:
/// ~/Library/Application Support/HiveMac. HIVEMAC_HOME overrides it (tests, a second set).
public struct AppDirs: Equatable, Sendable {
    public let data: URL

    public init(data: URL) { self.data = data }

    public static func standard(environment: [String: String] = ProcessInfo.processInfo.environment,
                                home: URL = FileManager.default.homeDirectoryForCurrentUser) -> AppDirs {
        if let env = environment["HIVEMAC_HOME"], !env.isEmpty {
            return AppDirs(data: URL(fileURLWithPath: (env as NSString).expandingTildeInPath))
        }
        return AppDirs(data: home.appendingPathComponent("Library/Application Support/HiveMac"))
    }

    public var settings: URL { data.appendingPathComponent("config/settings.json") }
    public var profiles: URL { data.appendingPathComponent("profiles") }
    public var logs: URL { data.appendingPathComponent("logs") }
    public var templates: URL { data.appendingPathComponent("templates") }
    public var userPaths: URL { data.appendingPathComponent("config/paths/user") }

    public func ensure() throws {
        let fm = FileManager.default
        for d in [settings.deletingLastPathComponent(), profiles, logs, templates,
                  userPaths.appendingPathComponent("to_field"), userPaths.appendingPathComponent("to_hive")] {
            try fm.createDirectory(at: d, withIntermediateDirectories: true)
        }
    }

    /// Finds a route file: the user's own recording wins over the built in Natro one.
    public func findPath(kind: String, field: String, variant: String = "walk", builtIn: URL) -> URL? {
        let slug = Paths.fieldSlug(field)
        let suffix = variant == "walk" ? "" : "_\(variant)"
        for base in [userPaths, builtIn] {
            let u = base.appendingPathComponent("\(kind)/\(slug)\(suffix).json")
            if FileManager.default.fileExists(atPath: u.path) { return u }
        }
        return nil
    }
}
