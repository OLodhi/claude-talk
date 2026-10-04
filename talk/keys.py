"""Notice a fresh press of Space or Esc while Claude is talking."""
import ctypes
from typing import Callable, Iterable

VK_SPACE = 0x20
VK_ESCAPE = 0x1B
_DOWN = 0x8000
_PRESSED_SINCE_LAST_CALL = 0x0001

_user32 = ctypes.WinDLL("user32")
_user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
_user32.GetAsyncKeyState.restype = ctypes.c_short


def _read_key_state(vk: int) -> int:
    return _user32.GetAsyncKeyState(vk) & 0xFFFF


class KeyWatcher:
    """pressed() is True for a press that starts after prime().

    A key already held when speech starts only counts once it has been released and pressed again."""

    def __init__(self, keys: Iterable[int] = (VK_SPACE, VK_ESCAPE), read: Callable[[int], int] = _read_key_state):
        self._keys = tuple(keys)
        self._read = read
        self._down: dict[int, bool] = {}

    def prime(self) -> None:
        for vk in self._keys:
            self._down[vk] = bool(self._read(vk) & _DOWN)  # reading also clears the "pressed since" bit

    def pressed(self) -> bool:
        fresh = False
        for vk in self._keys:
            state = self._read(vk)
            down = bool(state & _DOWN)
            if not self._down.get(vk, False) and (down or state & _PRESSED_SINCE_LAST_CALL):
                fresh = True
            self._down[vk] = down
        return fresh
