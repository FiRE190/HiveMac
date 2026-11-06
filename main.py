"""
BeeSwarm Local Macro — entry point.

Startup flow:
  1. scaffold_project()          — dirs, configs, git init (idempotent)
  2. init_logging()
  3. check_dependencies()        — warn on missing packages, auto-install if possible
  4. ConfigManager.load()
  5. ProfileManager (auto-loads last profile)
  6. FarmingService + Watchdog init
  7. MainWindow.mainloop()

The UI then runs the setup wizard / permission guide on first run.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


# ── Step 1: Scaffold (before any other import that might fail) ─────────

def _bootstrap() -> None:
    """Run project scaffold and dependency check before loading app modules."""
    from setup.auto_setup import run_full_setup
    run_full_setup(verbose=True)


def _check_and_install_deps() -> bool:
    """Check deps; auto-install missing ones into the current environment."""
    from setup.env_checker import check_all, install_missing_packages, print_report
    status = check_all()
    print_report(status)

    if status.missing_packages:
        print(f"\n[*] Auto-installing {len(status.missing_packages)} missing package(s)...")
        ok = install_missing_packages(status.missing_packages)
        if ok:
            print("[✓] Packages installed successfully\n")
        else:
            print("[!] Some packages could not be installed automatically.")
            print("    Run manually: pip install -r requirements.txt\n")
        return ok

    return status.packages_ok


# ── Main ──────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 50)
    print("  BeeSwarm Local Macro")
    print("=" * 50)
    print()

    # 1. Scaffold
    _bootstrap()

    # 2. Logging
    from utils.logger import init_logging, get_logger
    init_logging(str(ROOT / "logs"))
    log = get_logger("main")
    log.info("BeeSwarm Local Macro starting")

    # 3. Dependencies
    deps_ok = _check_and_install_deps()
    if not deps_ok:
        log.warning("Some dependencies are missing — functionality will be limited")

    # 4. Config
    from config.config_manager import get_config
    cfg = get_config()
    cfg.load()

    # 5. Services
    from services.farming_service import FarmingService
    farming_service = FarmingService()

    # 6. Watchdog
    from utils.watchdog import Watchdog
    watchdog = Watchdog(stop_callback=farming_service.stop)
    watchdog.start()

    # 7. Launch UI
    log.info("Launching control panel")
    from ui.main_window import MainWindow
    window = MainWindow(farming_service)
    window.mainloop()

    # Cleanup
    watchdog.stop()
    farming_service.stop()
    log.info("Macro shut down cleanly")


if __name__ == "__main__":
    main()
