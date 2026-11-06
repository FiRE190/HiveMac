import Foundation

// HiveMac.app's executable. It does not draw anything: it starts the bundled Python
// with main.py and stays alive until it exits. Being the bundle's real executable is
// what gives HiveMac its own identity in System Settings > Privacy & Security, so
// Screen Recording, Accessibility and Input Monitoring are granted to "HiveMac"
// instead of to whatever terminal you used.

let resources = Bundle.main.resourcePath ?? "."
let python = resources + "/venv/bin/python"
let appDir = resources + "/app"

func alert(_ title: String, _ text: String) {
    let esc = { (s: String) in s.replacingOccurrences(of: "\"", with: "\\\"") }
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
    p.arguments = ["-e", "display alert \"\(esc(title))\" message \"\(esc(text))\" as critical"]
    try? p.run()
    p.waitUntilExit()
}

guard FileManager.default.isExecutableFile(atPath: python),
      FileManager.default.fileExists(atPath: python) else {
    alert("HiveMac cannot start",
          "Its Python environment is missing or broken. This app needs Homebrew Python 3.12 with Tk: " +
          "brew install python@3.12 python-tk@3.12, then rebuild with scripts/install.sh.")
    exit(1)
}

let child = Process()
child.executableURL = URL(fileURLWithPath: python)
child.arguments = [appDir + "/main.py"]
child.currentDirectoryURL = URL(fileURLWithPath: appDir)
var env = ProcessInfo.processInfo.environment
env["PYTHONDONTWRITEBYTECODE"] = "1"   // never write into the signed bundle
env["PYTHONNOUSERSITE"] = "1"
env["HIVEMAC_BUNDLE"] = "1"
child.environment = env

// Quit from the Dock or the system: pass it on, then leave.
let signalSources: [DispatchSourceSignal] = [SIGTERM, SIGINT, SIGHUP].map { sig in
    signal(sig, SIG_IGN)
    let source = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    source.setEventHandler { child.terminate() }
    source.resume()
    return source
}
_ = signalSources

child.terminationHandler = { p in exit(p.terminationStatus) }
do {
    try child.run()
} catch {
    alert("HiveMac cannot start", "\(error)")
    exit(1)
}
dispatchMain()
