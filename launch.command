#!/bin/bash
# HiveMac launcher: double-click to run.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
echo "=================================================="
echo "  HiveMac"
echo "=================================================="
if [ ! -x venv/bin/python ]; then
  echo "[*] First run: installing..."
  bash install.sh || { read -p "Install failed. Press Enter to close..."; exit 1; }
fi
venv/bin/python -c "import customtkinter, numpy, mss, pynput, PIL" 2>/dev/null || venv/bin/pip install -q -r requirements.txt
venv/bin/python main.py
CODE=$?
if [ $CODE -ne 0 ]; then
  echo ""
  echo "[!] HiveMac exited with code $CODE. See logs/macro.log"
  read -p "Press Enter to close..."
fi
