"""Claude Code hook entry points: python -m talk.hooks <prompt|toggle|stop|session-end>

Reads the hook's JSON from stdin. Always exits 0 and never writes to stderr. The only output is
ASCII JSON on stdout: the /talk message (as a block reason) and the talk-mode nudge."""
import importlib.util
import json
import sys
import time
from typing import BinaryIO

from talk import control, paths, procs, switch
from talk.config import MODES, Config, load_config
from talk.log import get_logger
from talk.speakable import full_speech, summary_speech, to_speech

# Task 1 probe: input fields that may carry the typed prompt in UserPromptSubmit.
PROMPT_FIELDS = ("prompt", "user_prompt")
# Task 1 / Task 10: True only if the speaker is killed when the Stop hook process exits.
WAIT_FOR_SPEAKER = False

TALK_OFF = "🔇 Talk mode off."
MODE_DESCRIPTIONS = {
    "gist": "Claude will read the gist of each reply aloud",
    "full": "Claude will read whole replies aloud, except code",
    "summary": "Claude will read a short spoken summary of each reply",
}
NUDGES = {
    "gist": (
        "Talk mode is on: your reply will be read aloud to the user. Open with one or two plain sentences "
        "giving the gist, written the way you'd say it out loud. If the user is just chatting, keep the whole "
        "reply short and conversational. For technical work, put the details (code, file paths, lists) after "
        "the gist as usual; they stay on screen and won't be read out."
    ),
    "full": (
        "Talk mode is on (full mode): your whole reply will be read aloud to the user, except code blocks and "
        "tables. Write it the way you'd say it out loud, and keep it concise."
    ),
    "summary": (
        "Talk mode is on (summary mode): only a spoken summary of your reply is read aloud. Write your reply for "
        "the screen as usual, then end it with one final paragraph that starts with 🔊 and gives two to four "
        "short sentences written to be heard: the gist in plain words, no file paths, code or symbols, and any "
        "question you're asking the user."
    ),
}


def talk_on_message(mode: str) -> str:
    return f"🔊 Talk mode on ({mode}): {MODE_DESCRIPTIONS[mode]}. Tap Space or Esc to stop it talking."


def unknown_mode_message(word: str) -> str:
    return f'⚠\ufe0f Unknown talk mode "{word}". Use /talk, /talk gist, /talk full or /talk summary.'


def setup_broken() -> str:
    return (
        "⚠\ufe0f Talk mode couldn't start because the voice package isn't installed. "
        f"Run {paths.root() / 'setup.cmd'} to repair it."
    )


def tts_available() -> bool:
    return importlib.util.find_spec("edge_tts") is not None


def _block(reason: str) -> dict:
    return {"decision": "block", "reason": reason}


def _first_word(text) -> str:
    words = text.split() if isinstance(text, str) else []
    return words[0].lower() if words else ""


def _session_mode(session_id: str, cfg: Config) -> str:
    return switch.mode(session_id) or cfg.mode


def handle_toggle(payload: dict, argument: str | None = None) -> dict:
    """/talk toggles; /talk <mode> turns on in (or switches to) that mode. argument is the text after
    /talk from a raw prompt; when None it comes from UserPromptExpansion's command_args."""
    session_id = payload.get("session_id") or ""
    word = _first_word(payload.get("command_args") if argument is None else argument)
    if word and word not in MODES:
        return _block(unknown_mode_message(word))
    if not switch.is_on(session_id) and not tts_available():
        return _block(setup_broken())
    if word:
        switch.turn_on(session_id, word)  # same result however many hooks deliver it
        switch.cleanup_stale()
        return _block(talk_on_message(word))
    if switch.toggle(session_id, payload.get("prompt_id")):
        switch.cleanup_stale()  # the marker just set is brand new, so it is never swept
        return _block(talk_on_message(_session_mode(session_id, load_config())))
    control.stop_speaking()
    return _block(TALK_OFF)


def handle_prompt(payload: dict) -> dict | None:
    prompt = next((payload[f] for f in PROMPT_FIELDS if isinstance(payload.get(f), str)), "").strip()
    if prompt.split(" ", 1)[0] == "/talk":
        return handle_toggle(payload, prompt[len("/talk"):])
    if payload.get("prompt_source", "user_input") == "user_input":
        control.stop_speaking()
    session_id = payload.get("session_id") or ""
    if switch.is_on(session_id):
        switch.turn_on(session_id)  # keeps an active session's marker from looking stale
        nudge = NUDGES[_session_mode(session_id, load_config())]
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": nudge}}
    return None


def _speech_for(reply: str, mode: str, cfg: Config, session_id: str) -> tuple[str, str]:
    """The text to speak and the mode actually used (summary falls back to gist)."""
    if mode == "full":
        return full_speech(reply), "full"
    if mode == "summary":
        summary = summary_speech(reply)
        if summary:
            return summary, "summary"
        get_logger().info("session %s: no spoken summary; using gist", session_id[:8])
    return to_speech(reply, cfg.full_read_max_words, cfg.gist_max_words, cfg.closing_max_words), "gist"


def handle_stop(payload: dict) -> None:
    session_id = payload.get("session_id") or ""
    reply = (payload.get("last_assistant_message") or "").strip()
    if payload.get("agent_id") or not reply or not switch.is_on(session_id):
        return None
    cfg = load_config()
    speech, used = _speech_for(reply, _session_mode(session_id, cfg), cfg, session_id)
    pid = control.start_speaking(speech, session_id)
    get_logger().info("session %s: speaking %d words (%s)", session_id[:8], len(speech.split()), used)
    if WAIT_FOR_SPEAKER:
        while procs.is_alive(pid):
            time.sleep(0.2)
    return None


def handle_session_end(payload: dict) -> None:
    session_id = payload.get("session_id") or ""
    switch.turn_off(session_id)
    if session_id:
        control.stop_speaking(session_id=session_id)
    return None


HANDLERS = {
    "prompt": handle_prompt,
    "toggle": handle_toggle,
    "stop": handle_stop,
    "session-end": handle_session_end,
}


def main(argv: list[str] | None = None, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    stdin = stdin if stdin is not None else sys.stdin.buffer
    stdout = stdout if stdout is not None else sys.stdout.buffer
    try:
        raw = stdin.read().decode("utf-8-sig")
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
        result = HANDLERS[argv[0]](payload)
        if result is not None:
            stdout.write(json.dumps(result).encode("ascii"))
            stdout.flush()
    except Exception:
        try:
            get_logger().exception("hook %s failed", argv[:1])
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
