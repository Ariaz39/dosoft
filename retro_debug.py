"""Diagnostic journal for the Dofus Retro notification autofocus."""

from datetime import datetime
from pathlib import Path
import os
import threading


_lock = threading.Lock()
_MAX_LOG_SIZE = 1_500_000


def _log_path():
    configured = os.environ.get("DOSOFT_RETRO_DEBUG_LOG")
    if configured:
        return Path(configured)
    root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Dosoft" / "logs"
    return root / "retro-autofocus-debug.log"


def get_retro_debug_log_path():
    """Expose the active log location to the settings window."""
    return _log_path()


def begin_retro_debug_session():
    """Write an unmistakable session delimiter for a support capture."""
    write_retro_debug("========== AUTO-FOCUS RETRO : NOUVELLE SESSION ==========")


def write_retro_debug(message):
    """Append a compact, rotated diagnostic record for Retro autofocus."""
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            if path.exists() and path.stat().st_size > _MAX_LOG_SIZE:
                previous = path.with_suffix(".previous.log")
                if previous.exists():
                    previous.unlink()
                path.replace(previous)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            with path.open("a", encoding="utf-8") as log_file:
                log_file.write(f"{timestamp} {message}\n")
    except OSError:
        # The diagnostic must never interfere with the autofocus itself.
        pass
