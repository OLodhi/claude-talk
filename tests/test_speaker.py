import json
import os
import threading
import time

from talk import control, paths, speaker
from talk.speaker import Deps, speak


class FakePlayer:
    def __init__(self, log, path, polls=2):
        self.log, self.path, self.polls = log, path, polls

    def play(self):
        self.log.append(("play", self.path.name))

    def is_playing(self):
        self.polls -= 1
        return self.polls >= 0

    def close(self):
        self.log.append(("close", self.path.name))


class FakeProc:
    def __init__(self, polls=2):
        self.polls, self.killed = polls, False

    def poll(self):
        self.polls -= 1
        return None if self.polls >= 0 else 0

    def kill(self):
        self.killed = True


def ok_synth(text, path):
    path.write_bytes(b"mp3")


def failing_synth(text, path):
    raise RuntimeError("offline")


def slow_synth(text, path):
    time.sleep(1)
    path.write_bytes(b"mp3")


def make(tmp_path, synth=ok_synth, should_stop=lambda: False, fallback=True, player_polls=2, fallback_polls=2):
    log, fallbacks = [], []

    def start_fallback(text):
        proc = FakeProc(fallback_polls)
        fallbacks.append((text, proc))
        return proc

    deps = Deps(
        synthesize=synth,
        open_player=lambda path: FakePlayer(log, path, player_polls),
        start_fallback=start_fallback if fallback else None,
        should_stop=should_stop,
        work_dir=tmp_path,
    )
    return deps, log, fallbacks


def test_plays_every_chunk_in_order(tmp_path):
    deps, log, fallbacks = make(tmp_path)
    assert speak("One. Two.", deps) == "finished"
    assert log == [("play", "chunk0.mp3"), ("close", "chunk0.mp3"), ("play", "chunk1.mp3"), ("close", "chunk1.mp3")]
    assert fallbacks == []


def test_nothing_to_say(tmp_path):
    deps, log, _ = make(tmp_path)
    assert speak("", deps) == "finished"
    assert log == []


def test_synthesis_failure_falls_back_with_all_text(tmp_path):
    deps, log, fallbacks = make(tmp_path, synth=failing_synth)
    assert speak("One. Two.", deps) == "fallback"
    assert fallbacks[0][0] == "One. Two."
    assert log == []


def test_slow_first_audio_falls_back(tmp_path):
    deps, _, fallbacks = make(tmp_path, synth=slow_synth)
    assert speak("One.", deps, first_timeout=0.2) == "fallback"
    assert fallbacks[0][0] == "One."


def test_later_failure_falls_back_with_remaining_text(tmp_path):
    def second_fails(text, path):
        if text.startswith("Two"):
            raise RuntimeError("offline")
        path.write_bytes(b"mp3")

    deps, log, fallbacks = make(tmp_path, synth=second_fails)
    assert speak("One. Two. Three.", deps) == "fallback"
    assert log == [("play", "chunk0.mp3"), ("close", "chunk0.mp3")]
    assert fallbacks[0][0] == "Two. Three."


def test_player_error_falls_back(tmp_path):
    deps, _, fallbacks = make(tmp_path)

    def broken_player(path):
        raise OSError("no audio device")

    deps.open_player = broken_player
    assert speak("One. Two.", deps) == "fallback"
    assert fallbacks[0][0] == "One. Two."


def test_stop_during_playback(tmp_path):
    log = []
    deps, _, fallbacks = make(tmp_path, player_polls=100)
    deps.open_player = lambda path: FakePlayer(log, path, 100)
    deps.should_stop = lambda: bool(log)  # stop as soon as playback has started
    assert speak("One. Two.", deps) == "stopped"
    assert log == [("play", "chunk0.mp3"), ("close", "chunk0.mp3")]
    assert fallbacks == []


def test_stop_while_waiting_for_first_audio(tmp_path):
    deps, log, fallbacks = make(tmp_path, synth=slow_synth, should_stop=lambda: True)
    assert speak("One.", deps) == "stopped"
    assert log == []
    assert fallbacks == []


class ScriptedSynth:
    """Each call for a text runs its next scripted step: "ok", "fail", "slow-fail", "hang" or a delay in seconds."""

    def __init__(self, **scripts):
        self.scripts = {text: list(steps) for text, steps in scripts.items()}
        self.calls = []
        self.lock = threading.Lock()
        self.release = threading.Event()  # set at the end of a test so hung calls finish

    def __call__(self, text, path):
        with self.lock:
            self.calls.append(text)
            step = self.scripts[text].pop(0) if self.scripts.get(text) else "ok"
        if step == "hang":
            self.release.wait()
        elif step in ("fail", "slow-fail"):
            time.sleep(0.2 if step == "slow-fail" else 0)
            raise RuntimeError("offline")
        elif isinstance(step, float):
            time.sleep(step)
        path.write_bytes(b"mp3")


def test_a_slow_request_gets_a_backup_and_the_backup_plays(tmp_path):
    synth = ScriptedSynth(**{"One.": ["hang", "ok"]})
    deps, log, fallbacks = make(tmp_path, synth=synth)
    try:
        assert speak("One.", deps, first_timeout=1.0, backup_after=0.1) == "finished"
    finally:
        synth.release.set()
    assert log == [("play", "chunk0-backup.mp3"), ("close", "chunk0-backup.mp3")]
    assert fallbacks == []


def test_fast_requests_send_no_backup(tmp_path):
    synth = ScriptedSynth()
    deps, _, _ = make(tmp_path, synth=synth)
    assert speak("One. Two.", deps, backup_after=1.0) == "finished"
    assert sorted(synth.calls) == ["One.", "Two."]


def test_a_failed_backup_does_not_beat_a_slow_success(tmp_path):
    synth = ScriptedSynth(**{"One.": [0.3, "fail"]})
    deps, log, fallbacks = make(tmp_path, synth=synth)
    assert speak("One.", deps, first_timeout=2.0, backup_after=0.05) == "finished"
    assert log == [("play", "chunk0.mp3"), ("close", "chunk0.mp3")]
    assert fallbacks == []


def test_slow_failure_and_failed_backup_falls_back(tmp_path):
    synth = ScriptedSynth(**{"One.": ["slow-fail", "fail"]})
    deps, _, fallbacks = make(tmp_path, synth=synth)
    assert speak("One.", deps, first_timeout=2.0, backup_after=0.05) == "fallback"
    assert fallbacks[0][0] == "One."
    assert synth.calls == ["One.", "One."]


def test_the_next_chunk_is_requested_before_the_first_is_ready(tmp_path):
    two_requested = threading.Event()

    def synth(text, path):
        if text == "One.":
            assert two_requested.wait(timeout=2), "chunk 1 was not requested until chunk 0 was ready"
        else:
            two_requested.set()
        path.write_bytes(b"mp3")

    deps, log, fallbacks = make(tmp_path, synth=synth)
    assert speak("One. Two.", deps, first_timeout=3.0, backup_after=10.0) == "finished"
    assert log == [("play", "chunk0.mp3"), ("close", "chunk0.mp3"), ("play", "chunk1.mp3"), ("close", "chunk1.mp3")]
    assert fallbacks == []


def test_a_long_reply_is_fetched_a_few_chunks_ahead_not_all_at_once(tmp_path):
    # 50 sentences of ~220 characters: each is a chunk of its own (chunks hold up to 250)
    text = " ".join(f"Sentence {n} " + "word " * 40 + "ends here." for n in range(50))
    active, peak, lock = 0, 0, threading.Lock()

    def synth(text, path):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        path.write_bytes(b"mp3")

    deps, log, fallbacks = make(tmp_path, synth=synth, player_polls=1)
    assert speak(text, deps, backup_after=10.0) == "finished"
    assert [name for action, name in log if action == "play"] == [f"chunk{i}.mp3" for i in range(50)]
    assert peak <= speaker.LOOKAHEAD
    assert fallbacks == []


def test_stopping_early_leaves_later_chunks_unrequested(tmp_path):
    text = " ".join(f"Sentence {n} " + "word " * 40 + "ends here." for n in range(20))
    requested = []
    deps, log, _ = make(tmp_path, synth=lambda text, path: (requested.append(text), path.write_bytes(b"mp3")))
    deps.should_stop = lambda: bool(log)  # stop as soon as the first chunk starts playing
    assert speak(text, deps) == "stopped"
    assert len(requested) <= speaker.LOOKAHEAD


def test_no_fallback_configured(tmp_path):
    deps, _, _ = make(tmp_path, synth=failing_synth, fallback=False)
    assert speak("One.", deps) == "failed"


def test_stop_during_fallback_kills_it(tmp_path):
    deps, _, fallbacks = make(tmp_path, synth=failing_synth, fallback_polls=100)
    deps.should_stop = lambda: bool(fallbacks)  # stop as soon as the fallback voice has started
    assert speak("One.", deps) == "stopped"
    assert fallbacks[0][1].killed is True


def test_main_never_raises_and_cleans_up(monkeypatch, talk_home):
    job = paths.jobs_dir() / "abc.json"
    job.write_text(json.dumps({"token": "abc", "session_id": "s1", "text": "Hi."}), encoding="utf-8")
    (paths.state_dir() / "speaker.json").write_text(
        json.dumps({"pid": 1, "token": "abc", "session_id": "s1"}), encoding="utf-8"
    )

    def explode(text, token):
        raise RuntimeError("boom")

    monkeypatch.setattr(speaker, "_speak_job", explode)
    assert speaker.main([str(job)]) == 0
    assert not job.exists()
    assert control.current_speaker() is None
    assert "speaker failed" in (talk_home / "logs" / "talk.log").read_text(encoding="utf-8")


def test_main_passes_the_job_text_on(monkeypatch):
    job = paths.jobs_dir() / "def.json"
    job.write_text(json.dumps({"token": "def", "session_id": "s1", "text": "It costs £5."}), encoding="utf-8")
    spoken = []
    monkeypatch.setattr(speaker, "_speak_job", lambda text, token: spoken.append((text, token)) or "finished")
    assert speaker.main([str(job)]) == 0
    assert spoken == [("It costs £5.", "def")]


def test_sweep_removes_only_old_leftovers():
    old_dir = paths.state_dir() / "speak-old"
    old_dir.mkdir()
    (old_dir / "chunk0.mp3").write_bytes(b"x")
    fresh_dir = paths.state_dir() / "speak-fresh"
    fresh_dir.mkdir()
    old_job = paths.jobs_dir() / "old.json"
    old_job.write_text("{}", encoding="utf-8")
    two_hours_ago = time.time() - 7200
    for path in (old_dir, old_job):
        os.utime(path, (two_hours_ago, two_hours_ago))
    speaker._sweep_old_files()
    assert not old_dir.exists()
    assert not old_job.exists()
    assert fresh_dir.exists()
