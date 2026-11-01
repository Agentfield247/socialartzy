"""Logging helpers.

Every important action is written twice:

* to stdout, so it is visible in the GitHub Actions run log, and
* to ``logs/posting.log``, which the workflow commits back to the repository so
  you keep a permanent history even after the Actions run log expires.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Optional

from . import config

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%SZ"


class _UtcFormatter(logging.Formatter):
    """Formatter that always renders timestamps in UTC."""

    converter = time.gmtime


def get_logger(name: str = "artbot", log_file: Optional[Path] = None) -> logging.Logger:
    """Return a logger wired to stdout and to ``logs/posting.log``.

    Repeated calls with the same name reuse the already configured logger, so
    the file is never opened twice per process.
    """
    logger = logging.getLogger(name)
    if getattr(logger, "_socialartzy_configured", False):
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = _UtcFormatter(_LOG_FORMAT, _DATE_FORMAT)

    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    path = Path(log_file) if log_file else config.LOG_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, mode="a", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as exc:  # e.g. a read-only checkout: console logging still works
        logger.warning("Could not open log file %s (%s); continuing with console logging only", path, exc)

    logger._socialartzy_configured = True  # type: ignore[attr-defined]
    return logger


def log_banner(logger: logging.Logger, title: str) -> None:
    """Write a readable separator so runs are easy to find in the log."""
    logger.info("=" * 72)
    logger.info("%s | %s", title, config.utc_now())
    logger.info("=" * 72)