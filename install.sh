#!/bin/bash
# HiveMac installer for macOS: virtual environment + Python packages.
set -e
cd "$(dirname "$0")"

PYTHON=""
for candidate in python3.12 python3.11 python3.10; do
  if command -v "$candidate" &>/dev/null; then PYTHON="$candidate"; break; fi
done
if [ -z "$PYTHON" ]; then
  echo "[!] Python 3.10, 3.11 or 3.12 is required (newer versions have no OpenCV wheels yet)."
  echo "    brew install python@3.12"
  exit 1
fi
echo "[1/2] Creating virtual environment with $($PYTHON --version)..."
[ -d venv ] || "$PYTHON" -m venv venv
echo "[2/2] Installing Python packages..."
venv/bin/pip install --upgrade pip >/dev/null
venv/bin/pip install -r requirements.txt

echo ""
echo "=== Installation complete ==="
echo "Next:"
echo "  1. System Settings > Privacy & Security > Screen Recording: add your terminal (and Python)"
echo "  2. System Settings > Privacy & Security > Accessibility: add your terminal (and Python)"
echo "  3. Open Roblox in a window, start Bee Swarm Simulator, stand in your field"
echo "  4. Double-click launch.command (or: venv/bin/python main.py)"
