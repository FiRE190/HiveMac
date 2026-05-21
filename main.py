"""
BeeSwarm Local Macro — entry point.

Startup flow:
  1. scaffold_project() — create dirs, default files, git init
  2. init_logging()
  3. check_dependencies() — print warnings for missing packages
  4. ConfigManager.load()
  5. ProfileManager (auto-loads last profile)
  6. FarmingService init
  7. Watchdog start
  8. MainWindow.mainloop()
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent


# ------------------------------------------------------------------ #
# Step 1: Scaffold                                                     #
# ------------------------------------------------------------------ #

def scaffold_project() -> None:
    """Create all required directories and seed missing config files."""
    dirs = [
        "config", "state", "profiles", "detection", "ocr",
        "movement", "tasks", "services", "calibration", "ui",
        "utils", "debug", "logs", "templates",
    ]
    for d in dirs:
        (ROOT / d).mkdir(exist_ok=True)

    # Seed coordinates file
    coords_path = ROOT / "config" / "coordinates.json"
    if not coords_path.exists():
        coords_path.write_text("{}", encoding="utf-8")

    # Seed .gitignore
    gitignore_path = ROOT / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(
            "__pycache__/\n*.pyc\n*.pyo\n.env\nlogs/\ndebug/\n*.log\n.DS_Store\n",
            encoding="utf-8",
        )

    # Git init (safe to call multiple times)
    git_dir = ROOT / ".git"
    if not git_dir.exists():
        try:
            subprocess.run(["git", "init", str(ROOT)], check=True, capture_output=True)
            print("[scaffold] Git repository initialized")
        except Exception as e:
            print(f"[scaffold] Warning: git init failed: {e}")

    print("[scaffold] Project structure ready")


# ------------------------------------------------------------------ #
# Step 2: Dependency check                                             #
# ------------------------------------------------------------------ #

REQUIRED_PACKAGES = {
    "customtkinter": "customtkinter",
    "cv2":           "opencv-python",
    "pyautogui":     "pyautogui",
    "mss":           "mss",
    "PIL":           "Pillow",
    "pytesseract":   "pytesseract",
    "numpy":         "numpy",
    "pynput":        "pynput",
}


def check_dependencies() -> bool:
    missing = []
    for module, package in REQUIRED_PACKAGES.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if missing:
        print("\n[!] Missing Python packages:")
        for p in missing:
            print(f"    pip3 install {p}")
        print("\nRun:  bash install.sh\n")

    # Check tesseract
    try:
        result = subprocess.run(
            ["tesseract", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            raise FileNotFoundError
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("[!] tesseract not found. Run: brew install tesseract")
        missing.append("tesseract")

    return len(missing) == 0


# ------------------------------------------------------------------ #
# Step 3: macOS permissions advisory                                   #
# ------------------------------------------------------------------ #

def check_permissions() -> None:
    print("[*] Reminder: ensure these macOS permissions are granted:")
    print("    System Settings > Privacy & Security > Screen Recording → Python / Terminal")
    print("    System Settings > Privacy & Security > Accessibility → Python / Terminal")
    print("    (The macro cannot function without these permissions)\n")


# ------------------------------------------------------------------ #
# Main                                                                 #
# ------------------------------------------------------------------ #

def main() -> None:
    scaffold_project()

    # Bootstrap logging before anything else
    sys.path.insert(0, str(ROOT))
    from utils.logger import init_logging
    init_logging(str(ROOT / "logs"))

    from utils.logger import get_logger
    log = get_logger("main")
    log.info("BeeSwarm Local Macro starting up")

    ok = check_dependencies()
    if not ok:
        print("[!] Some dependencies are missing — OCR and detection will not work.")
        print("    The UI will still launch so you can install dependencies.\n")

    check_permissions()

    from config.config_manager import get_config
    cfg = get_config()
    cfg.load()

    from services.farming_service import FarmingService
    farming_service = FarmingService()

    from utils.watchdog import Watchdog
    watchdog = Watchdog(stop_callback=farming_service.stop)
    watchdog.start()

    log.info("Launching control panel")
    from ui.main_window import MainWindow
    window = MainWindow(farming_service)
    window.mainloop()

    # Cleanup on window close
    watchdog.stop()
    farming_service.stop()
    log.info("Macro shut down cleanly")


if __name__ == "__main__":
    main()
