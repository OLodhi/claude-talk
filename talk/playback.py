"""Play an audio file through Windows' built-in media control interface (MCI). No extra libraries."""
import ctypes
import itertools
import os
from ctypes import wintypes
from pathlib import Path

_winmm = ctypes.WinDLL("winmm")
_winmm.mciSendStringW.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.UINT, wintypes.HANDLE)
_winmm.mciSendStringW.restype = wintypes.DWORD
_winmm.mciGetErrorStringW.argtypes = (wintypes.DWORD, wintypes.LPWSTR, wintypes.UINT)
_aliases = itertools.count()


class PlaybackError(Exception):
    pass


def _mci(command: str) -> str:
    reply = ctypes.create_unicode_buffer(256)
    error = _winmm.mciSendStringW(command, reply, 255, None)
    if error:
        message = ctypes.create_unicode_buffer(256)
        _winmm.mciGetErrorStringW(error, message, 255)
        raise PlaybackError(f"{command!r} failed: {message.value}")
    return reply.value


class Mp3Player:
    """Plays one MP3 (or WAV) file. Use from the thread that created it."""

    def __init__(self, path: Path):
        self._alias = f"talk{os.getpid()}x{next(_aliases)}"
        _mci(f'open "{path}" type mpegvideo alias {self._alias}')

    def play(self) -> None:
        _mci(f"play {self._alias}")

    def is_playing(self) -> bool:
        return _mci(f"status {self._alias} mode") != "stopped"

    def close(self) -> None:
        for command in (f"stop {self._alias}", f"close {self._alias}"):
            try:
                _mci(command)
            except PlaybackError:
                pass
