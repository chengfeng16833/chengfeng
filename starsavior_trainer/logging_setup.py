"""Centralized logging for the Starsavior trainer.

Call ``get_logger(__name__)`` (or any short name) to obtain a logger that:
- prints INFO and above to the console, and
- writes DEBUG and above to a dated file ``logs/YYYY-MM-DD.log``.

Everything is UTF-8 so Chinese messages are not mangled. Configuration runs once
(idempotent) on the shared ``starsavior`` parent logger, so importing this from
many modules is safe.
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

_LOG_ROOT = "starsavior"
_configured = False

# logs/ lives at the project root (one level up from this package).
LOG_DIR = Path(__file__).resolve().parents[1] / "logs"


def _configure() -> None:
    global _configured
    if _configured:
        return

    logger = logging.getLogger(_LOG_ROOT)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # don't double-log through the root logger

    # --- Console handler: INFO and above ---
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    try:  # force UTF-8 so Chinese isn't garbled on Windows consoles
        console.stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    logger.addHandler(console)

    # --- File handler: DEBUG and above, one file per day ---
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(LOG_DIR / f"{date.today().isoformat()}.log", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
        )
        logger.addHandler(file_handler)
    except OSError:
        # File logging is best-effort; the console handler still works.
        pass

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured child logger under the shared ``starsavior`` parent."""
    _configure()
    return logging.getLogger(f"{_LOG_ROOT}.{name}")
