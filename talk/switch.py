"""Per-session talk mode, stored as one marker file per session in state/sessions/.

A marker's existence means talk is on. Its contents are the mode chosen with /talk <mode>, or empty
to follow the default mode in config.json."""
import time
from pathlib import Path

from talk import paths
from talk.config import MODES

STALE_AFTER_DAYS = 7


def _marker(session_id: str) -> Path:
    safe = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")
    if not safe:
        raise ValueError("session_id is empty")
    return paths.sessions_dir() / safe


def is_on(session_id: str) -> bool:
    try:
        return _marker(session_id).exists()
    except ValueError:
        return False


def mode(session_id: str) -> str | None:
    """The mode chosen for this session, or None to use the default."""
    try:
        word = _marker(session_id).read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None
    return word if word in MODES else None


def turn_on(session_id: str, mode: str | None = None) -> None:
    """Switch talk on. A given mode is stored; otherwise the marker keeps its contents (touch refreshes its age)."""
    marker = _marker(session_id)
    if mode is None:
        marker.touch()
    else:
        marker.write_text(mode, encoding="utf-8")


def turn_off(session_id: str) -> None:
    try:
        _marker(session_id).unlink(missing_ok=True)
    except ValueError:
        pass


def _last_speech_file(session_id: str) -> Path:
    marker = _marker(session_id)
    return marker.with_name(f"{marker.name}.last")  # markers never contain ".", so this never clashes


def save_last_speech(session_id: str, text: str) -> None:
    """Keep what was just spoken, for /talk again. Swept with the markers after STALE_AFTER_DAYS."""
    _last_speech_file(session_id).write_text(text, encoding="utf-8")


def last_speech(session_id: str) -> str | None:
    try:
        text = _last_speech_file(session_id).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    return text or None


def forget_last_speech(session_id: str) -> None:
    try:
        _last_speech_file(session_id).unlink(missing_ok=True)
    except ValueError:
        pass


def toggle(session_id: str, prompt_id: str | None = None) -> bool:
    """Flip talk mode and return the new state.

    The same /talk can reach us through two hooks (UserPromptSubmit and UserPromptExpansion)
    with the same prompt_id; the repeat changes nothing."""
    _marker(session_id)  # validates the id before anything changes
    last = paths.state_dir() / "last_toggle"
    key = f"{session_id}:{prompt_id}" if prompt_id else None
    if key and last.exists() and last.read_text(encoding="utf-8") == key:
        return is_on(session_id)
    if is_on(session_id):
        turn_off(session_id)
        new_state = False
    else:
        turn_on(session_id)
        new_state = True
    if key:
        last.write_text(key, encoding="utf-8")
    return new_state


def cleanup_stale(max_age_days: int = STALE_AFTER_DAYS, now: float | None = None) -> int:
    cutoff = (time.time() if now is None else now) - max_age_days * 86400
    removed = 0
    for marker in paths.sessions_dir().iterdir():
        try:
            if marker.stat().st_mtime < cutoff:
                marker.unlink()
                removed += 1
        except OSError:
            continue
    return removed
