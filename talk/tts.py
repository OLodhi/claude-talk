"""Speech synthesis: Microsoft's online neural voices, with the Windows built-in voice as a fallback."""
import asyncio
import subprocess
from pathlib import Path

from talk.procs import CREATE_NO_WINDOW


class TtsError(Exception):
    pass


def preload() -> None:
    """Import edge_tts up front. A missing package is left for synthesize to fail on, so the fallback voice still runs."""
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        pass


def synthesize(text: str, voice: str, rate: str, out_path: Path) -> None:
    """Write MP3 audio of text to out_path using edge-tts. Raises on any failure."""
    import edge_tts

    async def run() -> None:
        communicate = edge_tts.Communicate(text, voice, rate=rate, connect_timeout=5, receive_timeout=20)
        await communicate.save(str(out_path))

    asyncio.run(run())
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise TtsError("edge-tts returned no audio")


def windows_voice_command(text_file: Path) -> list[str]:
    path = str(text_file).replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Speak([IO.File]::ReadAllText('{path}', [Text.Encoding]::UTF8))"
    )
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]


def start_windows_voice(text: str, work_dir: Path) -> subprocess.Popen:
    """Start speaking text in the Windows built-in voice. Kill the returned process to stop it."""
    text_file = work_dir / "fallback.txt"
    text_file.write_text(text, encoding="utf-8")
    return subprocess.Popen(
        windows_voice_command(text_file),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )
