import json
import subprocess
import sys
import time
from pathlib import Path

from talk import control, paths, procs

FAKE = Path(__file__).with_name("fake_speaker.py")


def polite(job: Path) -> list[str]:
    return [sys.executable, str(FAKE), str(job), "polite"]


def stubborn(job: Path) -> list[str]:
    return [sys.executable, str(FAKE), str(job), "stubborn"]


def wait_until(condition, timeout=10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


def ready(job_token: str) -> bool:
    return (paths.jobs_dir() / f"{job_token}.ready").exists()


def test_start_records_the_current_speaker():
    pid = control.start_speaking("Hello.", "s1", command_for=polite)
    current = control.current_speaker()
    assert current["pid"] == pid
    assert current["session_id"] == "s1"
    control.stop_speaking()


def test_job_file_carries_the_text():
    captured = []

    def capture(job: Path) -> list[str]:
        captured.append(json.loads(job.read_text(encoding="utf-8")))
        return [sys.executable, "-c", "pass"]

    control.start_speaking("It costs £5.", "s1", command_for=capture)
    assert captured[0]["text"] == "It costs £5."
    assert captured[0]["session_id"] == "s1"
    assert captured[0]["token"] == control.current_speaker()["token"]


def test_stop_asks_a_polite_speaker_to_exit():
    pid = control.start_speaking("Hello.", "s1", command_for=polite)
    assert wait_until(lambda: ready(control.current_speaker()["token"]))
    assert control.stop_speaking() is True
    assert wait_until(lambda: not procs.is_alive(pid), timeout=2)
    assert control.current_speaker() is None


def test_stop_force_kills_a_stubborn_speaker():
    pid = control.start_speaking("Hello.", "s1", command_for=stubborn)
    assert wait_until(lambda: ready(control.current_speaker()["token"]))
    assert control.stop_speaking() is True
    assert wait_until(lambda: not procs.is_alive(pid), timeout=3)
    assert control.current_speaker() is None


def test_a_new_speaker_replaces_the_old_one():
    first = control.start_speaking("One.", "s1", command_for=stubborn)
    second = control.start_speaking("Two.", "s2", command_for=polite)
    assert wait_until(lambda: not procs.is_alive(first), timeout=3)
    assert control.current_speaker()["pid"] == second
    control.stop_speaking()


def test_stop_for_another_session_leaves_the_speaker_alone():
    pid = control.start_speaking("Hello.", "s1", command_for=polite)
    assert control.stop_speaking(session_id="s2") is False
    assert procs.is_alive(pid)
    control.stop_speaking()


def test_stop_with_no_speaker():
    assert control.stop_speaking() is False


def test_stale_record_with_dead_pid_is_cleared():
    result = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True)
    dead_pid = int(result.stdout)
    (paths.state_dir() / "speaker.json").write_text(
        json.dumps({"pid": dead_pid, "token": "old", "session_id": "s1"}), encoding="utf-8"
    )
    assert control.stop_speaking() is True
    assert control.current_speaker() is None


def test_should_stop_when_asked_or_superseded():
    assert control.should_stop("a") is False
    (paths.state_dir() / "speaker.json").write_text(json.dumps({"pid": 1, "token": "a"}), encoding="utf-8")
    assert control.should_stop("a") is False
    assert control.should_stop("b") is True
    (paths.state_dir() / "stop").write_text("a", encoding="utf-8")
    assert control.should_stop("a") is True


def test_speaker_command_uses_pythonw_from_this_environment(tmp_path):
    command = control.speaker_command(tmp_path / "job.json")
    assert command[0].lower().endswith(("pythonw.exe", "python.exe"))
    assert command[1:4] == ["-P", "-m", "talk.speaker"]
    assert command[4] == str(tmp_path / "job.json")


def test_reused_pid_is_not_killed():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        (paths.state_dir() / "speaker.json").write_text(
            json.dumps({"pid": proc.pid, "token": "old", "session_id": "s1", "started": time.time() - 3600}),
            encoding="utf-8",
        )
        assert control.stop_speaking() is True
        assert control.current_speaker() is None
        assert procs.is_alive(proc.pid)
    finally:
        proc.kill()
        proc.wait()


def test_started_at_reports_creation_time_or_none():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert abs(procs.started_at(proc.pid) - time.time()) < 5
    finally:
        proc.kill()
        proc.wait()
    result = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True)
    assert procs.started_at(int(result.stdout)) is None
