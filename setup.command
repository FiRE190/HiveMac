#!/bin/bash
# BeeSwarm Local Macro — one-time setup script (double-click to run)
# Run this once before first launch. launch.command also does this automatically.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "  BeeSwarm Local Macro — First-Time Setup"
echo "=================================================="
echo ""

# ── 1. Python ─────────────────────────────────────────────────────────
echo "[ Step 1/6 ] Checking Python..."
PYTHON=""
for candidate in python3.11 python3.10 python3.9 python3; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  [ERROR] Python 3 not found."
    echo "  Install: https://www.python.org/downloads/"
    read -p "Press Enter to exit..."
    exit 1
fi
echo "  [✓] $($PYTHON --version)"

# ── 2. Virtual environment ─────────────────────────────────────────────
echo ""
echo "[ Step 2/6 ] Setting up virtual environment..."
if [ ! -d "venv" ]; then
    $PYTHON -m venv venv && echo "  [✓] venv created at ./venv"
else
    echo "  [✓] venv already exists"
fi
source venv/bin/activate

# ── 3. Homebrew + Tesseract ────────────────────────────────────────────
echo ""
echo "[ Step 3/6 ] Installing Tesseract OCR..."
if command -v brew &>/dev/null; then
    if command -v tesseract &>/dev/null; then
        echo "  [✓] Tesseract already installed"
    else
        brew install tesseract && echo "  [✓] Tesseract installed"
    fi
else
    echo "  [!] Homebrew not found — cannot auto-install Tesseract."
    echo "      Install Homebrew: https://brew.sh"
    echo "      Then run: brew install tesseract"
fi

# ── 4. Python packages ─────────────────────────────────────────────────
echo ""
echo "[ Step 4/6 ] Installing Python packages..."
pip install -q --upgrade pip
pip install -r requirements.txt
echo "  [✓] Packages installed"

# ── 5. Project structure + git ─────────────────────────────────────────
echo ""
echo "[ Step 5/6 ] Initializing project structure..."
python -c "
import sys
sys.path.insert(0, '.')
from setup.auto_setup import run_full_setup
run_full_setup()
"
echo "  [✓] Project structure ready"

# ── 6. Permissions guidance ────────────────────────────────────────────
echo ""
echo "[ Step 6/6 ] macOS Permissions"
echo ""
echo "  ┌─────────────────────────────────────────────────────────┐"
echo "  │  REQUIRED: Two permissions must be granted manually     │"
echo "  ├─────────────────────────────────────────────────────────┤"
echo "  │                                                         │"
echo "  │  1. Screen Recording                                    │"
echo "  │     System Settings → Privacy & Security               │"
echo "  │     → Screen Recording → add Terminal + Python          │"
echo "  │                                                         │"
echo "  │  2. Accessibility                                       │"
echo "  │     System Settings → Privacy & Security               │"
echo "  │     → Accessibility → add Terminal + Python             │"
echo "  │                                                         │"
echo "  │  Without these the macro CANNOT see or control Roblox. │"
echo "  └─────────────────────────────────────────────────────────┘"
echo ""

# Open System Settings automatically
echo "  Opening System Settings > Privacy & Security..."
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"

echo ""
echo "=================================================="
echo "  Setup complete!"
echo "  Double-click launch.command to start the macro."
echo "=================================================="
echo ""
read -p "Press Enter to close..."
