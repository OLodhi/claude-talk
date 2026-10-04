import time

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


def test_no_fallback_configured(tmp_path):
    deps, _, _ = make(tmp_path, synth=failing_synth, fallback=False)
    assert speak("One.", deps) == "failed"


def test_stop_during_fallback_kills_it(tmp_path):
    deps, _, fallbacks = make(tmp_path, synth=failing_synth, fallback_polls=100)
    deps.should_stop = lambda: bool(fallbacks)  # stop as soon as the fallback voice has started
    assert speak("One.", deps) == "stopped"
    assert fallbacks[0][1].killed is True
