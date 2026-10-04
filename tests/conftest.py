import pytest


@pytest.fixture(autouse=True)
def talk_home(tmp_path, monkeypatch):
    """Every test gets its own empty Claude Talk home (state, logs, config)."""
    monkeypatch.setenv("CLAUDE_TALK_HOME", str(tmp_path))
    return tmp_path
