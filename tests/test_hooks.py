import io
import json

import pytest

from talk import control, hooks, switch


def run(event, payload):
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    out = io.BytesIO()
    assert hooks.main([event], stdin=io.BytesIO(raw), stdout=out) == 0
    return json.loads(out.getvalue()) if out.getvalue() else None


@pytest.fixture(autouse=True)
def calls(monkeypatch):
    record = {"stop": [], "start": []}
    monkeypatch.setattr(control, "stop_speaking", lambda session_id=None, **kw: record["stop"].append(session_id) or True)
    monkeypatch.setattr(
        control, "start_speaking", lambda text, session_id, **kw: record["start"].append((text, session_id)) or 4242
    )
    monkeypatch.setattr(hooks, "tts_available", lambda: True)
    return record


def block(reason):
    return {"decision": "block", "reason": reason}


def test_toggle_turns_talk_mode_on():
    assert run("toggle", {"session_id": "s1", "prompt_id": "p1"}) == block(hooks.TALK_ON)
    assert switch.is_on("s1")


def test_toggle_again_turns_it_off_and_stops_speech(calls):
    run("toggle", {"session_id": "s1", "prompt_id": "p1"})
    assert run("toggle", {"session_id": "s1", "prompt_id": "p2"}) == block(hooks.TALK_OFF)
    assert not switch.is_on("s1")
    assert calls["stop"] == [None]


def test_same_talk_command_through_both_hooks_toggles_once():
    typed = {"session_id": "s1", "prompt_id": "p1", "prompt": "/talk", "prompt_source": "user_input"}
    assert run("prompt", typed) == block(hooks.TALK_ON)
    assert run("toggle", {"session_id": "s1", "prompt_id": "p1"}) == block(hooks.TALK_ON)
    assert switch.is_on("s1")


def test_user_prompt_field_name_also_works():
    assert run("prompt", {"session_id": "s1", "user_prompt": "/talk"}) == block(hooks.TALK_ON)


def test_toggle_refuses_when_voice_package_is_missing(monkeypatch, talk_home):
    monkeypatch.setattr(hooks, "tts_available", lambda: False)
    result = run("toggle", {"session_id": "s1"})
    assert result["decision"] == "block"
    assert str(talk_home / "setup.cmd") in result["reason"]  # the repair step names this install's folder
    assert not switch.is_on("s1")


def test_prompt_in_talk_session_adds_the_nudge(calls):
    switch.turn_on("s1")
    result = run("prompt", {"session_id": "s1", "prompt": "hello", "prompt_source": "user_input"})
    assert result == {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": hooks.NUDGE}}
    assert calls["stop"] == [None]


def test_prompt_in_silent_session_outputs_nothing_but_still_silences(calls):
    assert run("prompt", {"session_id": "s1", "prompt": "hello", "prompt_source": "user_input"}) is None
    assert calls["stop"] == [None]


def test_turns_claude_starts_itself_do_not_silence(calls):
    run("prompt", {"session_id": "s1", "prompt": "", "prompt_source": "auto"})
    assert calls["stop"] == []


def test_stop_speaks_the_cleaned_reply(calls):
    switch.turn_on("s1")
    assert run("stop", {"session_id": "s1", "last_assistant_message": "**Done.** See `src/a/b.py`."}) is None
    assert calls["start"] == [("Done. See b.py.", "s1")]


def test_stop_reads_the_closing_of_a_long_reply(calls):
    switch.turn_on("s1")
    items = "\n".join(f"- Updated module number {i} so that it uses the new helper consistently" for i in range(12))
    reply = "Gist sentence for this reply.\n\n" + items + "\n\nWant me to open a pull request?"
    assert run("stop", {"session_id": "s1", "last_assistant_message": reply}) is None
    assert calls["start"] == [
        ("Gist sentence for this reply. The remainder of details are on screen. Want me to open a pull request?", "s1")
    ]


def test_stop_handles_non_ascii_reply(calls):
    switch.turn_on("s1")
    run("stop", {"session_id": "s1", "last_assistant_message": "It costs £5 — that’s fine."})
    assert calls["start"] == [("It costs £5 — that’s fine.", "s1")]


def test_stop_in_silent_session_is_quiet(calls):
    run("stop", {"session_id": "s1", "last_assistant_message": "Hello."})
    assert calls["start"] == []


def test_stop_with_empty_reply_is_quiet(calls):
    switch.turn_on("s1")
    run("stop", {"session_id": "s1", "last_assistant_message": "   "})
    assert calls["start"] == []


def test_subagent_replies_are_not_spoken(calls):
    switch.turn_on("s1")
    run("stop", {"session_id": "s1", "agent_id": "a1", "last_assistant_message": "Hello."})
    assert calls["start"] == []


def test_session_end_clears_the_switch_and_its_speech(calls):
    switch.turn_on("s1")
    run("session-end", {"session_id": "s1"})
    assert not switch.is_on("s1")
    assert calls["stop"] == ["s1"]


def test_output_is_ascii_json():
    out = io.BytesIO()
    hooks.main(["toggle"], stdin=io.BytesIO(b'{"session_id": "s1"}'), stdout=out)
    out.getvalue().decode("ascii")  # raises if any byte is non-ASCII
    assert json.loads(out.getvalue())["reason"] == hooks.TALK_ON


def test_bad_input_never_fails(capfd, talk_home):
    for event in ("prompt", "toggle", "stop", "session-end", "no-such-event"):
        assert run(event, b"not json") is None
        assert run(event, {}) is None
        assert run(event, b"") is None
    assert capfd.readouterr().err == ""
    assert "failed" in (talk_home / "logs" / "talk.log").read_text(encoding="utf-8")


def test_logging_failure_never_escapes(monkeypatch, capfd):
    """Verify that a logging failure in exception handler never escapes the hook."""
    class BrokenLogger:
        def exception(self, *args, **kwargs):
            raise OSError("log write failed")
        def info(self, *args, **kwargs):
            raise OSError("log write failed")

    monkeypatch.setattr(hooks, "get_logger", lambda: BrokenLogger())
    # Pass invalid JSON to trigger the exception handler
    result = hooks.main(["toggle"], stdin=io.BytesIO(b"not json"), stdout=io.BytesIO())
    assert result == 0
    assert capfd.readouterr().err == ""
