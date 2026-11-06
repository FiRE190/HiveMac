#!/bin/bash
# HiveMac — double-click launcher for macOS
# Place this file anywhere; it finds the project automatically.

# ── Locate project root (same folder as this script) ──────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "  HiveMac"
echo "=================================================="
echo ""

# ── Python check ──────────────────────────────────────────────────────
PYTHON=""
for candidate in python3.12 python3.11 python3.10; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python 3.10, 3.11 or 3.12 not found (newer versions lack OpenCV wheels)."
    echo "  Install one with: brew install python@3.12"
    read -p "Press Enter to exit..."
    exit 1
fi

PYTHON_VER=$($PYTHON --version 2>&1)
echo "[✓] Python: $PYTHON_VER"

# ── Virtual environment ────────────────────────────────────────────────
VENV_DIR="$SCRIPT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "[*] Creating virtual environment..."
    $PYTHON -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create virtual environment."
        read -p "Press Enter to exit..."
        exit 1
    fi
    echo "[✓] Virtual environment created"
fi

# Activate
source "$VENV_DIR/bin/activate"
echo "[✓] Virtual environment activated"

# ── Dependencies ───────────────────────────────────────────────────────
echo "[*] Checking Python packages..."
MISSING=$(python -c "
required = ['customtkinter','cv2','pyautogui','mss','PIL','numpy','pynput']
missing = []
for m in required:
    try: __import__(m)
    except ImportError: missing.append(m)
print(' '.join(missing))
" 2>/dev/null)

if [ -n "$MISSING" ]; then
    echo "[*] Installing missing packages..."
    pip install -q -r "$SCRIPT_DIR/requirements.txt"
    if [ $? -ne 0 ]; then
        echo "[ERROR] Package installation failed."
        echo "  Try running manually: pip install -r requirements.txt"
        read -p "Press Enter to exit..."
        exit 1
    fi
    echo "[✓] Packages installed"
else
    echo "[✓] All packages present"
fi

echo ""
echo "[*] Launching HiveMac..."
echo ""

# ── Launch ────────────────────────────────────────────────────────────
python "$SCRIPT_DIR/main.py"

# Keep terminal open on crash so error is visible
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "[!] App exited with error code $EXIT_CODE"
    echo "    Check logs/macro.log for details"
    read -p "Press Enter to close..."
fi
