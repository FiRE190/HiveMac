#!/bin/bash
# HiveMac installer for macOS: virtual environment + Python packages.
set -e
cd "$(dirname "$0")"

PYTHON=""
for candidate in python3.12 python3.13 python3.11 python3.10; do
  if command -v "$candidate" &>/dev/null && "$candidate" -c "import tkinter" &>/dev/null; then PYTHON="$candidate"; break; fi
done
if [ -z "$PYTHON" ]; then
  echo "[!] Need Python 3.10 to 3.13 with Tk. With Homebrew:"
  echo "    brew install python@3.12 python-tk@3.12"
  exit 1
fi
echo "[1/2] Creating virtual environment with $($PYTHON --version)..."
[ -d venv ] || "$PYTHON" -m venv venv
echo "[2/2] Installing Python packages..."
venv/bin/pip install --upgrade pip >/dev/null
venv/bin/pip install -r requirements.txt
rm -rf venv/lib/python3.*/site-packages/PyObjCTest

echo ""
echo "=== Installation complete ==="
echo "Next:"
echo "  1. System Settings > Privacy & Security > Screen Recording: add your terminal"
echo "  2. System Settings > Privacy & Security > Accessibility: add your terminal"
echo "  3. Open Roblox in a window, load Bee Swarm Simulator"
echo "  4. Double-click launch.command (or: venv/bin/python main.py) and follow the Calibrate tab"
