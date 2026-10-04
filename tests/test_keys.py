from talk.keys import VK_ESCAPE, VK_SPACE, KeyWatcher

DOWN = 0x8000
TAPPED = 0x0001


class ScriptedKeys:
    """Returns the next scripted GetAsyncKeyState value for each key (0 once the script runs out)."""

    def __init__(self, **scripts):
        self.scripts = {VK_SPACE: list(scripts.get("space", [])), VK_ESCAPE: list(scripts.get("esc", []))}

    def __call__(self, vk: int) -> int:
        script = self.scripts[vk]
        return script.pop(0) if script else 0


def watcher(**scripts) -> KeyWatcher:
    w = KeyWatcher(read=ScriptedKeys(**scripts))
    w.prime()
    return w


def test_nothing_pressed():
    w = watcher()
    assert w.pressed() is False


def test_space_pressed_after_start():
    w = watcher(space=[0, 0, DOWN])
    assert w.pressed() is False
    assert w.pressed() is True


def test_escape_pressed_after_start():
    w = watcher(esc=[0, DOWN])
    assert w.pressed() is True


def test_key_held_at_start_only_counts_after_release():
    w = watcher(space=[DOWN, DOWN | TAPPED, DOWN, 0, DOWN])
    assert w.pressed() is False  # still held (auto-repeat)
    assert w.pressed() is False  # still held
    assert w.pressed() is False  # released
    assert w.pressed() is True   # pressed again


def test_quick_tap_between_polls_counts():
    w = watcher(space=[0, TAPPED])
    assert w.pressed() is True
