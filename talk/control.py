"""Start and stop the one speaker process that may be talking at any time.

state/speaker.json records the current speaker (pid, token, session_id).
state/stop holds the token of a speaker that has been asked to stop."""
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Callable

from talk import paths, procs

STOP_WAIT_SECONDS = 0.5


def _speaker_file() -> Path:
    return paths.state_dir() / "speaker.json"


def _stop_file() -> Path:
    return paths.state_dir() / "stop"


def _stop_target() -> str | None:
    try:
        return _stop_file().read_text(encoding="utf-8").strip()
    except OSError:
        return None


def current_speaker() -> dict | None:
    try:
        data = json.loads(_speaker_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and isinstance(data.get("pid"), int) and isinstance(data.get("token"), str):
        return data
    return None


def should_stop(token: str) -> bool:
    """True when this speaker was asked to stop, or a newer speaker has taken over."""
    if _stop_target() == token:
        return True
    current = current_speaker()
    return current is not None and current["token"] != token


def clear_speaker(token: str) -> None:
    """Forget this speaker (if it is still the registered one) and its stop request."""
    current = current_speaker()
    if current and current["token"] == token:
        _speaker_file().unlink(missing_ok=True)
    if _stop_target() == token:
        _stop_file().unlink(missing_ok=True)


def stop_speaking(session_id: str | None = None, wait: float = STOP_WAIT_SECONDS) -> bool:
    """Stop the current speaker (only if it belongs to session_id, when given). True if one was stopped."""
    current = current_speaker()
    if current is None:
        return False
    if session_id is not None and current.get("session_id") != session_id:
        return False
    pid, token = current["pid"], current["token"]
    if procs.is_alive(pid):
        _stop_file().write_text(token, encoding="utf-8")
        deadline = time.monotonic() + wait
        while procs.is_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        if procs.is_alive(pid):
            procs.kill_tree(pid)
    clear_speaker(token)
    return True


def speaker_command(job_path: Path) -> list[str]:
    """pythonw.exe (no console window) from this same environment, running talk.speaker."""
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    return [str(pythonw if pythonw.exists() else python), "-m", "talk.speaker", str(job_path)]


def start_speaking(
    text: str, session_id: str, command_for: Callable[[Path], list[str]] = speaker_command
) -> int:
    """Silence any current speaker, then start a new one for text. Returns its pid."""
    stop_speaking()
    token = uuid.uuid4().hex
    job_path = paths.jobs_dir() / f"{token}.json"
    job_path.write_text(json.dumps({"token": token, "session_id": session_id, "text": text}), encoding="utf-8")
    pid = procs.spawn_detached(command_for(job_path))
    _speaker_file().write_text(
        json.dumps({"pid": pid, "token": token, "session_id": session_id, "started": time.time()}),
        encoding="utf-8",
    )
    return pid
