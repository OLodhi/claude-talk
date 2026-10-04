"""Windows process helpers: start a process that outlives us, check it, kill it with its children."""
import ctypes
import subprocess
from ctypes import wintypes

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NO_WINDOW = 0x08000000
_SYNCHRONIZE = 0x00100000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_WAIT_TIMEOUT = 0x102

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
_kernel32.GetProcessTimes.argtypes = (
    wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
)
_kernel32.GetProcessTimes.restype = wintypes.BOOL
_EPOCH_OFFSET_SECONDS = 11644473600  # 1601-01-01 to 1970-01-01


def spawn_detached(args: list[str]) -> int:
    """Start args with no console and outside our job (if allowed), so it survives the hook exiting."""
    base = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    options = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    try:
        return subprocess.Popen(args, creationflags=base | CREATE_BREAKAWAY_FROM_JOB, **options).pid
    except OSError:
        return subprocess.Popen(args, creationflags=base, **options).pid


def is_alive(pid: int) -> bool:
    handle = _kernel32.OpenProcess(_SYNCHRONIZE | _PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        return _kernel32.WaitForSingleObject(handle, 0) == _WAIT_TIMEOUT
    finally:
        _kernel32.CloseHandle(handle)


def kill_tree(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, check=False,
    )


def started_at(pid: int) -> float | None:
    """Process creation time as Unix epoch seconds (UTC), or None if it can't be read."""
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        if not _kernel32.GetProcessTimes(
            handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)
        ):
            return None
        ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
        return ticks / 1e7 - _EPOCH_OFFSET_SECONDS
    finally:
        _kernel32.CloseHandle(handle)
