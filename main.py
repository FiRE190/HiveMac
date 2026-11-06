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


def main() -> None:
    from setup.auto_setup import run_full_setup
    run_full_setup()

    from utils.logger import get_logger, init_logging
    init_logging(str(ROOT / "logs"))
    log = get_logger("main")
    log.info("HiveMac starting")

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
    window.mainloop()

    watchdog.stop()
    service.stop()
    service.stop_remote()
    log.info("HiveMac shut down")


if __name__ == "__main__":
    main()
