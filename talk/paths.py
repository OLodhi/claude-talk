"""Where Claude Talk keeps its files. CLAUDE_TALK_HOME overrides the project folder (used by tests)."""
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def root() -> Path:
    return Path(os.environ.get("CLAUDE_TALK_HOME", _PROJECT_ROOT))


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_dir() -> Path:
    return _ensure(root() / "state")


def sessions_dir() -> Path:
    return _ensure(state_dir() / "sessions")


def jobs_dir() -> Path:
    return _ensure(state_dir() / "jobs")


def log_file() -> Path:
    return _ensure(root() / "logs") / "talk.log"


def config_file() -> Path:
    return root() / "config.json"
