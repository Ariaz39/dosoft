"""Small, dependency-free rotating log writer used by optional diagnostics."""

from __future__ import annotations

from pathlib import Path
import queue
import threading


_locks_guard = threading.Lock()
_locks = {}
_async_lines = queue.Queue(maxsize=2048)
_async_worker_lock = threading.Lock()
_async_worker = None


def _lock_for(path):
    key = str(Path(path).resolve())
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def append_rotating(path, line, max_bytes=1_000_000, backup_count=2):
    """Append one line and rotate bounded backups. Diagnostics never raise."""
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with _lock_for(target):
            encoded_size = len((str(line) + "\n").encode("utf-8"))
            if target.exists() and target.stat().st_size + encoded_size > max_bytes:
                for index in range(max(1, int(backup_count)), 0, -1):
                    source = target if index == 1 else target.with_name(f"{target.name}.{index - 1}")
                    destination = target.with_name(f"{target.name}.{index}")
                    if not source.exists():
                        continue
                    if destination.exists():
                        destination.unlink()
                    source.replace(destination)
            with target.open("a", encoding="utf-8") as stream:
                stream.write(str(line) + "\n")
        return True
    except (OSError, UnicodeError, ValueError):
        return False


def _write_async_lines():
    while True:
        arguments = _async_lines.get()
        try:
            append_rotating(*arguments)
        finally:
            _async_lines.task_done()


def append_rotating_async(path, line, max_bytes=1_000_000, backup_count=2):
    """Queue diagnostics so UI and global-hotkey callbacks never wait on disk."""
    global _async_worker
    with _async_worker_lock:
        if _async_worker is None or not _async_worker.is_alive():
            _async_worker = threading.Thread(
                target=_write_async_lines,
                name="dosoft-log-writer",
                daemon=True,
            )
            _async_worker.start()
    try:
        _async_lines.put_nowait((path, line, max_bytes, backup_count))
        return True
    except queue.Full:
        return False
