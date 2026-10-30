"""The emulator's processes (Citra, Azahar or Lime3DS on Windows), for the recorder to read the game in them
(gamegui/process.py)."""

import ctypes
import sys
from collections.abc import Iterable
from ctypes import wintypes

EMULATORS = ("citra-qt.exe", "citra.exe", "azahar.exe", "azahar-qt.exe", "lime3ds.exe", "lime3ds-gui.exe")


class _ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]


def emulator_pids(names: Iterable[str] = EMULATORS) -> list[int]:
    """The process ids of the running programs named `names` (Citra, Azahar or Lime3DS; Windows' process list,
    elsewhere none)."""
    if sys.platform != "win32":
        return []
    wanted = {name.lower() for name in names}
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = k32.CreateToolhelp32Snapshot(0x2, 0)             # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return []
    out = []
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        more = k32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            if entry.szExeFile.lower() in wanted:
                out.append(entry.th32ProcessID)
            more = k32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snapshot)
    return out
