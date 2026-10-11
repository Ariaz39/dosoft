"""Small dependency-free Windows process checks used by setup diagnostics."""

import ctypes
import os


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def is_process_running(executable_name):
    """Return whether an executable is running without requiring admin rights."""
    expected = str(executable_name).casefold()
    process_ids = (ctypes.c_ulong * 4096)()
    bytes_returned = ctypes.c_ulong()
    if not ctypes.windll.psapi.EnumProcesses(
        process_ids, ctypes.sizeof(process_ids), ctypes.byref(bytes_returned)
    ):
        return False
    count = bytes_returned.value // ctypes.sizeof(ctypes.c_ulong)
    for process_id in process_ids[:count]:
        if not process_id:
            continue
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, process_id
        )
        if not handle:
            continue
        try:
            size = ctypes.c_ulong(32768)
            path = ctypes.create_unicode_buffer(size.value)
            if ctypes.windll.kernel32.QueryFullProcessImageNameW(
                handle, 0, path, ctypes.byref(size)
            ) and os.path.basename(path.value).casefold() == expected:
                return True
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    return False
