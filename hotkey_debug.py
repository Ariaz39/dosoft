import logging
import os
from logging.handlers import RotatingFileHandler


_LOGGER = None


def get_hotkey_debug_log_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    log_dir = os.path.join(base, "Dosoft", "logs")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "hotkey-debug.log")


def _get_logger():
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    logger = logging.getLogger("dosoft.hotkeys")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(
            get_hotkey_debug_log_path(), maxBytes=512_000, backupCount=2, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    _LOGGER = logger
    return logger


def write_hotkey_debug(message, level="info"):
    try:
        logger = _get_logger()
        getattr(logger, level, logger.info)(str(message))
    except Exception:
        # Diagnostics must never break shortcut capture.
        pass
