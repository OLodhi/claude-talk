"""Runs setup.cmd for real on a copy of the project, so it needs the internet (pip downloads edge-tts)."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
NOT_SHIPPED = shutil.ignore_patterns(".git", ".venv", "state", "logs", "probe", "*.egg-info", "__pycache__", ".pytest_cache")

pytestmark = pytest.mark.skipif(
    os.environ.get("TALK_NETWORK_TESTS") != "1", reason="set TALK_NETWORK_TESTS=1 to run setup.cmd (downloads packages)"
)


def run_setup(project: Path, claude_dir: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_TALK_HOME"}  # the copy must find its own folder
    return subprocess.run(
        [str(project / "setup.cmd"), "-ClaudeDir", str(claude_dir)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env, timeout=600,
    )


def test_setup_installs_a_fresh_copy_and_is_safe_to_rerun(tmp_path):
    project = tmp_path / "claude-talk"
    shutil.copytree(PROJECT, project, ignore=NOT_SHIPPED)
    claude_dir = tmp_path / "claude"
    venv_python = project / ".venv" / "Scripts" / "python.exe"

    first = run_setup(project, claude_dir)
    assert first.returncode == 0, first.stdout + first.stderr

    settings = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
    commands = [hook["command"] for groups in settings["hooks"].values() for group in groups for hook in group["hooks"]]
    assert commands == [str(venv_python)] * 4
    assert str(project / "logs" / "talk.log") in (claude_dir / "commands" / "talk.md").read_text(encoding="utf-8")
    imported = subprocess.run(
        [str(venv_python), "-P", "-c", "import edge_tts, talk; print(talk.__file__)"],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert imported.returncode == 0, imported.stderr
    assert Path(imported.stdout.strip()).is_relative_to(project)  # code runs from the copy, so git pull updates it

    second = run_setup(project, claude_dir)
    assert second.returncode == 0, second.stdout + second.stderr
    assert json.loads((claude_dir / "settings.json").read_text(encoding="utf-8")) == settings
