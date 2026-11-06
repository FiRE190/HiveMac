#!/bin/bash
# Builds HiveMac.app and zips it for a GitHub Release. Does not publish anything.
# The zip only runs on Macs with Homebrew Python 3.12 + Tk at the same path
# (brew install python@3.12 python-tk@3.12).
# Usage: scripts/release.sh
set -euo pipefail
cd "$(dirname "$0")/.."

scripts/make-app.sh
VERSION="$(/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' build/HiveMac.app/Contents/Info.plist)"
ZIP="build/HiveMac-${VERSION}.zip"

rm -f "$ZIP"
# ditto keeps the bundle structure and signature intact, unlike plain zip.
ditto -c -k --keepParent build/HiveMac.app "$ZIP"
echo "Made $ZIP"
echo "To publish: gh release create v${VERSION} \"$ZIP\" --title \"HiveMac ${VERSION}\" --notes-file CHANGELOG.md"
