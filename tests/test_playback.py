import time
import wave
from pathlib import Path

import pytest

from talk.playback import Mp3Player, PlaybackError


def silent_wav(path: Path, seconds: float = 0.3) -> Path:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b"\x00\x00" * int(16000 * seconds))
    return path


def test_plays_a_file_to_the_end(tmp_path):
    player = Mp3Player(silent_wav(tmp_path / "silence.wav"))
    player.play()
    deadline = time.monotonic() + 3
    while player.is_playing():
        assert time.monotonic() < deadline, "playback never finished"
        time.sleep(0.05)
    player.close()


def test_close_is_safe_to_repeat(tmp_path):
    player = Mp3Player(silent_wav(tmp_path / "silence.wav"))
    player.play()
    player.close()
    player.close()


def test_missing_file_raises(tmp_path):
    with pytest.raises(PlaybackError):
        Mp3Player(tmp_path / "missing.mp3")
