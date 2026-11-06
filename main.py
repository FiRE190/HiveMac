"""
HiveMac entry point.

  1. make sure the folders and default files exist
  2. logging
  3. config and last profile
  4. FarmingService (owns the loop), watchdog with the F9 stop key, remote page
  5. control panel window
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


def _set_app_name() -> None:
    """Menu bar shows the process name; inside the app bundle make it HiveMac, not Python."""
    try:
        from Foundation import NSBundle
        info = NSBundle.mainBundle().infoDictionary()
        info["CFBundleName"] = "HiveMac"
    except Exception:
        pass


def _set_app_icon() -> None:
    """Dock icon from the bundle's icns (the Python process would show the Python rocket)."""
    icon = ROOT.parent / "HiveMac.icns"
    if not icon.exists():
        return
    try:
        from AppKit import NSApplication, NSImage
        img = NSImage.alloc().initWithContentsOfFile_(str(icon))
        if img is not None:
            NSApplication.sharedApplication().setApplicationIconImage_(img)
    except Exception:
        pass


def main() -> None:
    _set_app_name()
    from setup.auto_setup import run_full_setup
    run_full_setup()

    from utils import appdirs
    from utils.logger import get_logger, init_logging
    from utils.version import app_version
    init_logging(str(appdirs.logs_dir()))
    log = get_logger("main")
    log.info("HiveMac %s starting (data in %s)", app_version(), appdirs.data_dir())

    from setup.env_checker import check_all, print_report
    status = check_all()
    print_report(status)

    from config.config_manager import get_config
    get_config().load()

    from services.farming_service import FarmingService
    service = FarmingService()
    service.start_remote()

    from utils.watchdog import Watchdog
    watchdog = Watchdog(stop_callback=service.stop)
    watchdog.start()

    from ui.main_window import MainWindow
    window = MainWindow(service)
    _set_app_icon()
    window.mainloop()

    watchdog.stop()
    service.stop()
    service.stop_remote()
    log.info("HiveMac shut down")


if __name__ == "__main__":
    main()
