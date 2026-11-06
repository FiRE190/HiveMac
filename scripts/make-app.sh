#!/bin/bash
# Builds HiveMac.app into ./build/ (code, a Python environment, a launcher, an icon).
# Usage: scripts/make-app.sh
set -euo pipefail
cd "$(dirname "$0")/.."

APP_NAME="HiveMac"
BUNDLE_ID="app.hivemac.macro"   # placeholder, change if you own a domain to use
VERSION="$(tr -d '[:space:]' < VERSION)"
APP="build/${APP_NAME}.app"
RES="$APP/Contents/Resources"

# Python 3.10 to 3.13 with Tk (customtkinter needs it).
PYTHON=""
for candidate in python3.12 python3.13 python3.11 python3.10; do
  if command -v "$candidate" &>/dev/null && "$candidate" -c "import tkinter" &>/dev/null; then PYTHON="$(command -v "$candidate")"; break; fi
done
if [ -z "$PYTHON" ]; then
  echo "[!] Need Python 3.10 to 3.13 with Tk. With Homebrew: brew install python@3.12 python-tk@3.12"
  exit 1
fi

rm -rf "$APP" "build/${APP_NAME}.iconset"
mkdir -p "$APP/Contents/MacOS" "$RES/app"

echo "[1/5] launcher"
swiftc -O scripts/launcher.swift -o "$APP/Contents/MacOS/${APP_NAME}"

echo "[2/5] icon"
swift scripts/make-icon.swift "build/${APP_NAME}.iconset"
iconutil -c icns "build/${APP_NAME}.iconset" -o "$RES/${APP_NAME}.icns"
rm -rf "build/${APP_NAME}.iconset"

echo "[3/5] code"
rsync -a --exclude '__pycache__' --exclude '*.pyc' \
  --include 'config/' --include 'config/default_config.json' --include 'config/__init__.py' \
  --include 'config/config_manager.py' --include 'config/paths/' --include 'config/paths/natro/***' \
  --exclude 'config/*' \
  --include 'main.py' --include 'VERSION' --include 'LICENSE' --include 'requirements.txt' \
  --include 'calibration/***' --include 'detection/***' --include 'execution/***' --include 'macro/***' \
  --include 'movement/***' --include 'remote/***' --include 'services/***' --include 'setup/***' \
  --include 'state/***' --include 'ui/***' --include 'utils/***' \
  --include 'profiles/' --include 'profiles/__init__.py' --include 'profiles/profile_manager.py' --include 'profiles/default_profile.json' \
  --exclude 'profiles/*' \
  --exclude '*' ./ "$RES/app/"

echo "[4/5] Python environment ($($PYTHON --version))"
"$PYTHON" -m venv "$RES/venv"
"$RES/venv/bin/pip" install --quiet --upgrade pip
"$RES/venv/bin/pip" install --quiet -r requirements.txt
rm -rf "$RES"/venv/lib/python3.*/site-packages/PyObjCTest
find "$RES/venv" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key><string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key><string>${BUNDLE_ID}</string>
    <key>CFBundleExecutable</key><string>${APP_NAME}</string>
    <key>CFBundleIconFile</key><string>${APP_NAME}</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>${VERSION}</string>
    <key>CFBundleVersion</key><string>${VERSION}</string>
    <key>LSMinimumSystemVersion</key><string>13.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSHumanReadableCopyright</key><string>MIT licence. Not affiliated with Roblox.</string>
</dict>
</plist>
PLIST

echo "[5/5] signing"
# Ad-hoc signature: enough to run on the Mac that built it. The identity changes with every
# build, so macOS may ask for the permissions again after a rebuild.
codesign --force --sign - "$APP"
echo "Built $APP ($(du -sh "$APP" | cut -f1))"
