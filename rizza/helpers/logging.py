"""Logging configuration for rizza."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

console = Console(stderr=True)


def resolve_log_level(level):
    """Resolve log level string to logging int constant."""
    if isinstance(level, int):
        return level
    mapping = {
        "trace": 5,
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }
    return mapping.get(str(level).lower(), logging.INFO)


def setup_logging(console_level=logging.INFO, file_level=None, log_path=None):
    """Configure logging with RichHandler for console and rotating file handler.

    Call this once at CLI startup; call again to reconfigure with a log file.
    """
    console_int = resolve_log_level(console_level)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    console_handler = RichHandler(
        console=console,
        rich_tracebacks=True,
        show_time=True,
        show_path=console_int <= logging.DEBUG,
        markup=True,
    )
    console_handler.setLevel(console_int)
    console_handler.setFormatter(logging.Formatter("%(message)s", datefmt="%d%b %H:%M:%S"))
    root.addHandler(console_handler)

    if log_path and file_level is not None:
        file_int = resolve_log_level(file_level)
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(path, maxBytes=int(1e9), backupCount=3)
        file_handler.setLevel(file_int)
        file_handler.setFormatter(
            logging.Formatter(
                "[%(levelname)s %(asctime)s %(name)s:%(lineno)d] %(message)s",
                datefmt="%d%b %H:%M:%S",
            )
        )
        root.addHandler(file_handler)


# Basic console-only setup so logs work before CLI configures a file handler
setup_logging()
