import subprocess
import sys


def test_hook_ignores_a_decoy_talk_package_in_the_working_directory(tmp_path):
    decoy = tmp_path / "talk"
    decoy.mkdir()
    (decoy / "__init__.py").write_text("", encoding="utf-8")
    (decoy / "hooks.py").write_text(
        "from pathlib import Path\nPath('DECOY_RAN').write_text('x')\nprint('DECOY')\n", encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, "-P", "-m", "talk.hooks", "prompt"],
        cwd=tmp_path,
        input=b'{"session_id": "proc-test", "prompt": "hello", "prompt_source": "user_input"}',
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""
    assert not (tmp_path / "DECOY_RAN").exists()
