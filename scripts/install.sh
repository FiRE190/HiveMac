#!/bin/bash
# Builds HiveMac and installs it to /Applications (or ~/Applications if that is not writable).
# Usage: scripts/install.sh
set -euo pipefail
cd "$(dirname "$0")/.."

scripts/make-app.sh

DEST="/Applications"
[ -w "$DEST" ] || DEST="$HOME/Applications"
mkdir -p "$DEST"

# Quit a running copy so the new one can replace it.
osascript -e 'tell application "HiveMac" to quit' 2>/dev/null || true
pkill -f 'HiveMac.app/Contents/MacOS/HiveMac' 2>/dev/null || true
sleep 1

rm -rf "$DEST/HiveMac.app"
cp -R build/HiveMac.app "$DEST/HiveMac.app"
# Remove the build copy so Spotlight and Launchpad show only one HiveMac.
rm -rf build/HiveMac.app
echo "Installed $DEST/HiveMac.app"
echo "Open it from Finder or Launchpad. Your settings are in ~/Library/Application Support/HiveMac."
echo "First run: System Settings > Privacy & Security, allow HiveMac for Screen Recording,"
echo "Accessibility and Input Monitoring, then reopen it."
