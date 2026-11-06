// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "HiveMac",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "HiveMacCore", targets: ["HiveMacCore"]),
        .library(name: "HiveMacPlatform", targets: ["HiveMacPlatform"]),
        .executable(name: "hivemac-probe", targets: ["hivemac-probe"]),
        .executable(name: "HiveMac", targets: ["HiveMacApp"]),
    ],
    targets: [
        .target(name: "HiveMacCore"),
        .target(name: "HiveMacPlatform", dependencies: ["HiveMacCore"]),
        .executableTarget(name: "hivemac-probe", dependencies: ["HiveMacCore", "HiveMacPlatform"]),
        .executableTarget(name: "HiveMacApp", dependencies: ["HiveMacCore", "HiveMacPlatform"]),
        .testTarget(name: "HiveMacCoreTests", dependencies: ["HiveMacCore"]),
    ],
    swiftLanguageModes: [.v5]
)
