from pathlib import Path

from talk import paths


def test_everything_lives_under_home(talk_home):
    assert paths.root() == talk_home
    assert paths.state_dir() == talk_home / "state"
    assert paths.sessions_dir() == talk_home / "state" / "sessions"
    assert paths.jobs_dir() == talk_home / "state" / "jobs"
    assert paths.log_file() == talk_home / "logs" / "talk.log"
    assert paths.config_file() == talk_home / "config.json"


def test_directories_are_created(talk_home):
    assert paths.sessions_dir().is_dir()
    assert paths.jobs_dir().is_dir()
    assert paths.log_file().parent.is_dir()


def test_default_root_is_the_project_folder(monkeypatch):
    monkeypatch.delenv("CLAUDE_TALK_HOME")
    assert paths.root() == Path(paths.__file__).resolve().parent.parent
