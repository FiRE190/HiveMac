"""
Logging system: rotating file log + thread-safe queue that feeds the UI console.
Use get_logger(name) everywhere; the UI polls LOG_QUEUE via after().
"""
import logging
import logging.handlers
import queue
import os
from pathlib import Path

LOG_QUEUE: queue.Queue = queue.Queue(maxsize=2000)
_initialized = False


class _QueueHandler(logging.Handler):
    """Pushes formatted records into LOG_QUEUE for the UI to consume."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            LOG_QUEUE.put_nowait((record.levelno, msg))
        except Exception:
            pass


def _setup_root_logger(log_dir: str) -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_path = os.path.join(log_dir, "macro.log")

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logging.INFO)

    qh = _QueueHandler()
    qh.setFormatter(fmt)
    qh.setLevel(logging.DEBUG)

    root.addHandler(fh)
    root.addHandler(ch)
    root.addHandler(qh)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def init_logging(log_dir: str = "logs") -> None:
    _setup_root_logger(log_dir)
