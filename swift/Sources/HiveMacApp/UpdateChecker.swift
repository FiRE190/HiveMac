import SwiftUI
import AppKit

/// Asks GitHub for the newest release and compares it with this app's version.
/// Nothing is downloaded or installed here: "Download" opens the release page.
@MainActor
final class UpdateChecker: ObservableObject {
    enum Status: Equatable {
        case idle, checking, upToDate
        case available(version: String, url: URL)
        case unavailable(String)
    }

    static let repo = "FiRE190/HiveMac"
    private static let autoKey = "checkForUpdatesOnLaunch"

    @Published var status: Status = .idle
    @Published var autoCheck: Bool {
        didSet { UserDefaults.standard.set(autoCheck, forKey: Self.autoKey) }
    }

    let current: String = (Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String) ?? "0.0.0"

    init() {
        autoCheck = UserDefaults.standard.object(forKey: Self.autoKey) as? Bool ?? true
    }

    func checkOnLaunch() { if autoCheck { Task { await check() } } }

    func check() async {
        status = .checking
        guard let url = URL(string: "https://api.github.com/repos/\(Self.repo)/releases/latest") else { return }
        var req = URLRequest(url: url, timeoutInterval: 10)
        req.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            if code == 404 { status = .unavailable("No public releases yet."); return }
            guard code == 200,
                  let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let tag = json["tag_name"] as? String,
                  let page = (json["html_url"] as? String).flatMap(URL.init(string:)) else {
                status = .unavailable("GitHub answered with \(code)."); return
            }
            let latest = tag.hasPrefix("v") ? String(tag.dropFirst()) : tag
            status = Self.isNewer(latest, than: current) ? .available(version: latest, url: page) : .upToDate
        } catch {
            status = .unavailable("Could not reach GitHub.")
        }
    }

    static func isNewer(_ a: String, than b: String) -> Bool {
        let x = a.split(separator: ".").map { Int($0) ?? 0 }, y = b.split(separator: ".").map { Int($0) ?? 0 }
        for i in 0..<max(x.count, y.count) {
            let l = i < x.count ? x[i] : 0, r = i < y.count ? y[i] : 0
            if l != r { return l > r }
        }
        return false
    }
}

struct UpdateRow: View {
    @ObservedObject var checker: UpdateChecker

    private var message: String {
        switch checker.status {
        case .idle: return "Version \(checker.current)."
        case .checking: return "Checking."
        case .upToDate: return "Version \(checker.current). You have the newest."
        case .available(let v, _): return "Version \(v) is available. You have \(checker.current)."
        case .unavailable(let why): return "Version \(checker.current). \(why)"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            SettingRow(label: "Updates", hint: message) {
                HStack {
                    if case .available(_, let url) = checker.status {
                        Button("Download") { NSWorkspace.shared.open(url) }.buttonStyle(QuietButtonStyle(tint: Theme.honeyText))
                    }
                    Button("Check now") { Task { await checker.check() } }.buttonStyle(QuietButtonStyle())
                }
            }
            SettingRow(label: "Check on launch") {
                Toggle("Yes", isOn: $checker.autoCheck).toggleStyle(.checkbox)
            }
        }
    }
}
