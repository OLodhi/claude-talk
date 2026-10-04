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
    assert run("toggle", {"session_id": "s1", "prompt_id": "p1"}) == block(hooks.talk_on_message("gist"))
    assert switch.is_on("s1")


def test_toggle_again_turns_it_off_and_stops_speech(calls):
    run("toggle", {"session_id": "s1", "prompt_id": "p1"})
    assert run("toggle", {"session_id": "s1", "prompt_id": "p2"}) == block(hooks.TALK_OFF)
    assert not switch.is_on("s1")
    assert calls["stop"] == [None]


def test_same_talk_command_through_both_hooks_toggles_once():
    typed = {"session_id": "s1", "prompt_id": "p1", "prompt": "/talk", "prompt_source": "user_input"}
    assert run("prompt", typed) == block(hooks.talk_on_message("gist"))
    assert run("toggle", {"session_id": "s1", "prompt_id": "p1"}) == block(hooks.talk_on_message("gist"))
    assert switch.is_on("s1")


def test_user_prompt_field_name_also_works():
    assert run("prompt", {"session_id": "s1", "user_prompt": "/talk"}) == block(hooks.talk_on_message("gist"))


def test_toggle_refuses_when_voice_package_is_missing(monkeypatch, talk_home):
    monkeypatch.setattr(hooks, "tts_available", lambda: False)
    result = run("toggle", {"session_id": "s1"})
    assert result["decision"] == "block"
    assert str(talk_home / "setup.cmd") in result["reason"]  # the repair step names this install's folder
    assert not switch.is_on("s1")


def test_prompt_in_talk_session_adds_the_nudge(calls):
    switch.turn_on("s1")
    result = run("prompt", {"session_id": "s1", "prompt": "hello", "prompt_source": "user_input"})
    assert result == {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": hooks.NUDGES["gist"]}}
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
    assert json.loads(out.getvalue())["reason"] == hooks.talk_on_message("gist")


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


def log_text(talk_home):
    return (talk_home / "logs" / "talk.log").read_text(encoding="utf-8")


def test_talk_with_a_mode_turns_on_in_that_mode():
    result = run("toggle", {"session_id": "s1", "prompt_id": "p1", "command_args": "summary"})
    assert result == block(hooks.talk_on_message("summary"))
    assert switch.is_on("s1")
    assert switch.mode("s1") == "summary"


def test_talk_with_a_mode_switches_without_turning_off(calls):
    run("toggle", {"session_id": "s1", "prompt_id": "p1"})
    result = run("toggle", {"session_id": "s1", "prompt_id": "p2", "command_args": "Full"})
    assert result == block(hooks.talk_on_message("full"))
    assert switch.is_on("s1")
    assert switch.mode("s1") == "full"
    assert calls["stop"] == []


def test_mode_from_a_raw_prompt_with_odd_spacing_and_capitals():
    typed = {"session_id": "s1", "prompt_id": "p1", "prompt": "/talk   SUMMARY  ", "prompt_source": "user_input"}
    assert run("prompt", typed) == block(hooks.talk_on_message("summary"))
    assert switch.mode("s1") == "summary"


def test_same_mode_command_through_both_hooks_gives_the_same_message():
    typed = {"session_id": "s1", "prompt_id": "p1", "prompt": "/talk full", "prompt_source": "user_input"}
    assert run("prompt", typed) == block(hooks.talk_on_message("full"))
    expanded = {"session_id": "s1", "prompt_id": "p1", "command_args": "full"}
    assert run("toggle", expanded) == block(hooks.talk_on_message("full"))
    assert switch.is_on("s1")
    assert switch.mode("s1") == "full"


def test_unknown_mode_changes_nothing():
    assert run("toggle", {"session_id": "s1", "command_args": "sumary"}) == block(hooks.unknown_mode_message("sumary"))
    assert not switch.is_on("s1")
    switch.turn_on("s1", "full")
    run("toggle", {"session_id": "s1", "command_args": "loud"})
    assert switch.is_on("s1")
    assert switch.mode("s1") == "full"


def test_mode_command_refuses_when_voice_package_is_missing(monkeypatch, talk_home):
    monkeypatch.setattr(hooks, "tts_available", lambda: False)
    result = run("toggle", {"session_id": "s1", "command_args": "full"})
    assert str(talk_home / "setup.cmd") in result["reason"]
    assert not switch.is_on("s1")


def test_plain_talk_announces_the_default_mode_from_config(talk_home):
    (talk_home / "config.json").write_text('{"mode": "full"}', encoding="utf-8")
    assert run("toggle", {"session_id": "s1", "prompt_id": "p1"}) == block(hooks.talk_on_message("full"))
    assert switch.mode("s1") is None  # the session keeps following the default


@pytest.mark.parametrize("mode", ["gist", "full", "summary"])
def test_nudge_matches_the_session_mode(mode):
    switch.turn_on("s1", mode)
    result = run("prompt", {"session_id": "s1", "prompt": "hello", "prompt_source": "user_input"})
    assert result["hookSpecificOutput"]["additionalContext"] == hooks.NUDGES[mode]


def test_summary_nudge_names_the_marker_the_speaker_looks_for():
    assert "🔊" in hooks.NUDGES["summary"]


def test_stop_in_summary_mode_speaks_only_the_summary(calls):
    switch.turn_on("s1", "summary")
    reply = "Long screen text about the change, with `code` and src/a/b.py.\n\n🔊 The fix is in. Shall I push it?"
    run("stop", {"session_id": "s1", "last_assistant_message": reply})
    assert calls["start"] == [("The fix is in. Shall I push it?", "s1")]


def test_summary_mode_without_a_summary_falls_back_to_gist(calls, talk_home):
    switch.turn_on("s1", "summary")
    run("stop", {"session_id": "s1", "last_assistant_message": "**Done.** See `src/a/b.py`.\n\n🔊"})
    assert calls["start"] == [("Done. See b.py.", "s1")]
    assert "no spoken summary" in log_text(talk_home)


def test_fallback_is_logged_with_the_session_and_the_mode_actually_used(calls, talk_home):
    switch.turn_on("s1", "summary")
    run("stop", {"session_id": "s1", "last_assistant_message": "Plain reply with no summary."})
    log = log_text(talk_home)
    assert "session s1: no spoken summary; using gist" in log
    assert "speaking 5 words (gist)" in log
    assert "(summary)" not in log


def test_full_mode_speaks_the_whole_reply(calls):
    switch.turn_on("s1", "full")
    items = "\n".join(f"- Updated module number {i} so that it uses the new helper consistently" for i in range(12))
    reply = "Gist sentence for this reply.\n\n" + items + "\n\nWant me to open a pull request?"
    run("stop", {"session_id": "s1", "last_assistant_message": reply})
    expected = (
        "Gist sentence for this reply. "
        + " ".join(f"Updated module number {i} so that it uses the new helper consistently." for i in range(12))
        + " Want me to open a pull request?"
    )
    assert calls["start"] == [(expected, "s1")]


def test_session_without_a_mode_follows_config_on_each_reply(calls, talk_home):
    switch.turn_on("s1")
    (talk_home / "config.json").write_text('{"mode": "summary"}', encoding="utf-8")
    run("stop", {"session_id": "s1", "last_assistant_message": "Body text.\n\n🔊 Short version."})
    assert calls["start"] == [("Short version.", "s1")]


def test_speed_is_saved_as_a_percentage():
    from talk import speed

    result = run("toggle", {"session_id": "s1", "command_args": "speed 150"})
    assert result == block("\u23e9 Speed set to 150%. It applies from the next reply.")
    assert speed.load() == 150
    assert not switch.is_on("s1")  # setting the speed never turns talk on or off


def test_speed_from_a_raw_prompt_with_a_percent_sign():
    from talk import speed

    typed = {"session_id": "s1", "prompt_id": "p1", "prompt": "/talk Speed 120%", "prompt_source": "user_input"}
    assert run("prompt", typed) == block("\u23e9 Speed set to 120%. It applies from the next reply.")
    assert speed.load() == 120


@pytest.mark.parametrize("asked, saved, note", [
    ("300", 200, "the fastest Microsoft's voice goes"),
    ("20", 50, "the slowest Microsoft's voice goes"),
])
def test_speed_outside_the_voice_range_is_capped(asked, saved, note):
    from talk import speed

    result = run("toggle", {"session_id": "s1", "command_args": f"speed {asked}"})
    assert result == block(f"\u23e9 Speed set to {saved}% ({note}). It applies from the next reply.")
    assert speed.load() == saved


def test_speed_on_its_own_reports_the_current_speed():
    assert run("toggle", {"session_id": "s1", "command_args": "speed"}) == block(
        "\u23e9 Speed is 100%. Use /talk speed 50 to 200 to change it; 100 is normal."
    )


def test_speed_that_is_not_a_number_changes_nothing():
    from talk import speed

    assert run("toggle", {"session_id": "s1", "command_args": "speed fast"}) == block(
        '\u26a0\ufe0f "fast" isn\'t a speed. Use /talk speed with a number from 50 to 200, for example /talk speed 150.'
    )
    assert speed.load() is None


def test_stop_remembers_what_it_spoke():
    switch.turn_on("s1")
    run("stop", {"session_id": "s1", "last_assistant_message": "**Done.** See `src/a/b.py`."})
    assert switch.last_speech("s1") == "Done. See b.py."


@pytest.mark.parametrize("word", ["again", "repeat", "AGAIN"])
def test_talk_again_replays_the_last_speech(calls, word):
    switch.turn_on("s1")
    run("stop", {"session_id": "s1", "last_assistant_message": "The fix is in."})
    calls["start"].clear()
    assert run("toggle", {"session_id": "s1", "command_args": word}) == block("\U0001F501 Repeating the last reply.")
    assert calls["start"] == [("The fix is in.", "s1")]


def test_talk_again_works_after_talk_is_turned_off(calls):
    switch.turn_on("s1")
    run("stop", {"session_id": "s1", "last_assistant_message": "The fix is in."})
    switch.turn_off("s1")
    calls["start"].clear()
    typed = {"session_id": "s1", "prompt_id": "p9", "prompt": "/talk again", "prompt_source": "user_input"}
    assert run("prompt", typed) == block("\U0001F501 Repeating the last reply.")
    assert calls["start"] == [("The fix is in.", "s1")]
    assert not switch.is_on("s1")


def test_talk_again_with_nothing_spoken_yet(calls):
    assert run("toggle", {"session_id": "s1", "command_args": "again"}) == block("\U0001F501 Nothing to repeat yet.")
    assert calls["start"] == []


def test_session_end_forgets_the_last_speech():
    switch.turn_on("s1")
    run("stop", {"session_id": "s1", "last_assistant_message": "The fix is in."})
    run("session-end", {"session_id": "s1"})
    assert switch.last_speech("s1") is None


def test_unknown_option_lists_every_command():
    message = hooks.unknown_mode_message("loud")
    for option in ("/talk gist", "/talk full", "/talk summary", "/talk again", "/talk speed"):
        assert option in message
