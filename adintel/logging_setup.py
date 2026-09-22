"""Console + per-run file logging."""

import logging
import sys
from pathlib import Path

from adintel.config import settings

LOG_DIR = settings.PROJECT_ROOT / "logs"


def setup(run_uid, platform, retailer_slug):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"{run_uid}_{retailer_slug}_{platform}.log"

    logger = logging.getLogger("adintel")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console)

    to_file = logging.FileHandler(path, encoding="utf-8")
    to_file.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s"))
    logger.addHandler(to_file)

    return logger, path


def get():
    return logging.getLogger("adintel")
