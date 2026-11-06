// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "HiveMac",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "HiveMacCore", targets: ["HiveMacCore"]),
    ],
    targets: [
        .target(name: "HiveMacCore"),
        .testTarget(name: "HiveMacCoreTests", dependencies: ["HiveMacCore"]),
    ],
    swiftLanguageModes: [.v5]
)
