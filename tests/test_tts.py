import os
from pathlib import Path

import pytest

from talk import tts


def test_preload_imports_edge_tts_without_raising():
    import sys

    tts.preload()
    assert "edge_tts" in sys.modules


def test_windows_voice_command_reads_the_text_file_as_utf8():
    command = tts.windows_voice_command(Path(r"C:\work\fallback.txt"))
    assert command[:4] == ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
    assert "System.Speech" in command[4]
    assert r"ReadAllText('C:\work\fallback.txt', [Text.Encoding]::UTF8)" in command[4]


def test_windows_voice_command_escapes_quotes():
    command = tts.windows_voice_command(Path(r"C:\it's\fallback.txt"))
    assert r"'C:\it''s\fallback.txt'" in command[4]


@pytest.mark.skipif(os.environ.get("TALK_NETWORK_TESTS") != "1", reason="set TALK_NETWORK_TESTS=1 to call Microsoft's voice service")
def test_synthesize_writes_mp3(tmp_path):
    out = tmp_path / "hello.mp3"
    tts.synthesize("Talk mode is working.", "en-GB-SoniaNeural", "+0%", out)
    assert out.stat().st_size > 1000
