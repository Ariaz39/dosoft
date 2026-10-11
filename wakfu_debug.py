"""Optional diagnostic trace for the WAKFU autofocus beta."""

from datetime import datetime
import os
import threading
from log_utils import append_rotating


_lock = threading.Lock()


def write_wakfu_debug(message):
    """Append a compact diagnostic record when beta tracing is enabled."""
    path = os.environ.get("DOSOFT_WAKFU_DEBUG_LOG")
    if not path:
        return
    try:
        with _lock:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            append_rotating(path, f"{timestamp} {message}", max_bytes=750_000, backup_count=2)
    except Exception:
        pass
