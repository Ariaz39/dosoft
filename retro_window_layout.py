"""Window arrangements for the Dofus Retro desktop module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import ctypes
from ctypes import wintypes
import math
import os
from pathlib import Path

import win32api
import win32con
import win32gui
from log_utils import append_rotating


DWMWA_EXTENDED_FRAME_BOUNDS = 9


class _Rect(ctypes.Structure):
    _fields_ = (
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    )


LOG_PATH = (
    Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    / "DOSOFT"
    / "retro-window-layout.log"
)


@dataclass(frozen=True)
class WindowLayoutResult:
    requested: int
    changed: int
    failed: int
    mode: str

    @property
    def ok(self) -> bool:
        return self.changed > 0 and self.failed == 0


def grid_rectangles(work_area, count: int, max_columns: int = 4):
    """Return column-major rectangles; eight windows become a 4 × 2 grid."""
    if count <= 0:
        return []
    left, top, right, bottom = (int(value) for value in work_area)
    columns = min(max(1, int(max_columns)), count)
    rows = int(math.ceil(count / columns))
    total_width = max(1, right - left)
    total_height = max(1, bottom - top)
    x_edges = [left + (total_width * index) // columns for index in range(columns + 1)]
    y_edges = [top + (total_height * index) // rows for index in range(rows + 1)]
    rectangles = []
    for index in range(count):
        column = index // rows
        row = index % rows
        rectangles.append((
            x_edges[column],
            y_edges[row],
            x_edges[column + 1] - x_edges[column],
            y_edges[row + 1] - y_edges[row],
        ))
    return rectangles


def _valid_handles(handles):
    seen = set()
    valid = []
    for value in handles:
        try:
            hwnd = int(value)
        except (TypeError, ValueError):
            continue
        if hwnd in seen or not win32gui.IsWindow(hwnd):
            continue
        seen.add(hwnd)
        valid.append(hwnd)
    return valid


def _record(message):
    append_rotating(
        LOG_PATH,
        f"[{datetime.now():%Y-%m-%d %H:%M:%S.%f}] {message}",
        max_bytes=750_000,
        backup_count=2,
    )


def _is_maximized(hwnd):
    try:
        return win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMAXIMIZED
    except Exception:
        return False


def _visible_frame_insets(hwnd):
    """Return the invisible resize margins around a DWM-managed window."""
    try:
        outer_left, outer_top, outer_right, outer_bottom = win32gui.GetWindowRect(hwnd)
        visible = _Rect()
        result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(int(hwnd)),
            wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
            ctypes.byref(visible),
            wintypes.DWORD(ctypes.sizeof(visible)),
        )
        if result != 0:
            return (0, 0, 0, 0)
        insets = (
            max(0, visible.left - outer_left),
            max(0, visible.top - outer_top),
            max(0, outer_right - visible.right),
            max(0, outer_bottom - visible.bottom),
        )
        # Reject stale or abnormal measurements instead of displacing a client.
        return insets if all(value <= 32 for value in insets) else (0, 0, 0, 0)
    except Exception:
        return (0, 0, 0, 0)


def outer_rect_for_visible_slot(slot, insets):
    """Expand an outer Win32 rectangle so its visible DWM frame fills *slot*."""
    left, top, width, height = (int(value) for value in slot)
    inset_left, inset_top, inset_right, inset_bottom = (
        max(0, int(value)) for value in insets
    )
    return (
        left - inset_left,
        top - inset_top,
        width + inset_left + inset_right,
        height + inset_top + inset_bottom,
    )


def maximize_windows(handles):
    windows = _valid_handles(handles)
    changed = 0
    failed = 0
    for hwnd in windows:
        try:
            # SW_MAXIMIZE is idempotent: already-maximized clients remain so.
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            changed += 1
        except Exception as error:
            failed += 1
            _record(f"MAXIMIZE_ERROR hwnd={hwnd:#x} error={type(error).__name__}:{error}")
    result = WindowLayoutResult(len(windows), changed, failed, "maximize")
    _record(f"MAXIMIZE requested={result.requested} changed={changed} failed={failed}")
    return result


def tile_windows(handles, anchor_hwnd=None, max_columns: int = 4):
    windows = _valid_handles(handles)
    if not windows:
        return WindowLayoutResult(0, 0, 0, "tile")
    anchor = int(anchor_hwnd) if anchor_hwnd and win32gui.IsWindow(int(anchor_hwnd)) else windows[0]
    monitor = win32api.MonitorFromWindow(anchor, win32con.MONITOR_DEFAULTTONEAREST)
    work_area = win32api.GetMonitorInfo(monitor)["Work"]
    rectangles = grid_rectangles(work_area, len(windows), max_columns=max_columns)
    flags = (
        win32con.SWP_NOACTIVATE
        | win32con.SWP_NOZORDER
        | win32con.SWP_SHOWWINDOW
        | win32con.SWP_FRAMECHANGED
    )
    changed = 0
    failed = 0
    for hwnd, (left, top, width, height) in zip(windows, rectangles):
        try:
            # Restore maximized/minimized clients before applying their tile.
            if win32gui.IsIconic(hwnd) or _is_maximized(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            insets = _visible_frame_insets(hwnd)
            outer_rect = outer_rect_for_visible_slot(
                (left, top, width, height), insets
            )
            win32gui.SetWindowPos(hwnd, 0, *outer_rect, flags)
            changed += 1
            _record(
                f"TILE_WINDOW hwnd={hwnd:#x} slot={(left, top, width, height)} "
                f"insets={insets} outer={outer_rect}"
            )
        except Exception as error:
            failed += 1
            _record(f"TILE_ERROR hwnd={hwnd:#x} error={type(error).__name__}:{error}")
    result = WindowLayoutResult(len(windows), changed, failed, "tile")
    _record(
        f"TILE requested={result.requested} changed={changed} failed={failed} "
        f"work_area={tuple(work_area)} columns={min(max_columns, len(windows))}"
    )
    return result
