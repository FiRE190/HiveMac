#!/bin/bash
# BeeSwarm Local Macro — one-command installer for macOS
set -e

echo "=== BeeSwarm Local Macro Installer ==="
echo ""

# Check for Homebrew
if ! command -v brew &>/dev/null; then
  echo "[!] Homebrew not found. Install from https://brew.sh"
  exit 1
fi

# Install Tesseract OCR
echo "[1/3] Installing Tesseract OCR via Homebrew..."
brew install tesseract

# Upgrade pip
echo "[2/3] Upgrading pip..."
python3 -m pip install --upgrade pip

# Install Python dependencies
echo "[3/3] Installing Python packages..."
pip3 install -r "$(dirname "$0")/requirements.txt"

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "  1. Grant Screen Recording permission:"
echo "     System Settings > Privacy & Security > Screen Recording > add Terminal / Python"
echo ""
echo "  2. Grant Accessibility permission:"
echo "     System Settings > Privacy & Security > Accessibility > add Terminal / Python"
echo ""
echo "  3. Launch the macro:"
echo "     python3 main.py"
echo ""
echo "  4. Open Roblox, start Bee Swarm Simulator"
echo "  5. Click 'Calibrate' in the control panel and record your key coordinates"
echo "  6. Press START to begin farming"
