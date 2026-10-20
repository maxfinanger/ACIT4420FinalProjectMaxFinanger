"""Logging configuration: events and errors go to logs/busbidder.log."""
import logging
from pathlib import Path

from .paths import PROJECT_ROOT


def setup_logging(log_dir: str = str(PROJECT_ROOT / "logs")) -> logging.Logger:
    Path(log_dir).mkdir(exist_ok=True)
    logger = logging.getLogger("busbidder")
    if not logger.handlers:  # avoid duplicate handlers on re-import
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(Path(log_dir) / "busbidder.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(handler)
    return logger
