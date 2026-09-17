"""Optional diagnostic trace for the WAKFU autofocus beta."""

from datetime import datetime
import os
import threading


_lock = threading.Lock()


def write_wakfu_debug(message):
    """Append a compact diagnostic record when beta tracing is enabled."""
    path = os.environ.get("DOSOFT_WAKFU_DEBUG_LOG")
    if not path:
        return
    try:
        with _lock, open(path, "a", encoding="utf-8") as log_file:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            log_file.write(f"{timestamp} {message}\n")
    except OSError:
        pass
