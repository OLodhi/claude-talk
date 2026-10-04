"""Claude Code hook entry points: python -m talk.hooks <prompt|toggle|stop|session-end>

Reads the hook's JSON from stdin. Always exits 0 and never writes to stderr. The only output is
ASCII JSON on stdout: the /talk message (as a block reason) and the talk-mode nudge."""
import importlib.util
import json
import sys
import time
from typing import BinaryIO

from talk import control, procs, switch
from talk.config import load_config
from talk.log import get_logger
from talk.speakable import to_speech

# Task 1 probe: input fields that may carry the typed prompt in UserPromptSubmit.
PROMPT_FIELDS = ("prompt", "user_prompt")
# Task 1 / Task 10: True only if the speaker is killed when the Stop hook process exits.
WAIT_FOR_SPEAKER = False

TALK_ON = "🔊 Talk mode on: Claude will read replies aloud. Tap Space or Esc to stop it talking."
TALK_OFF = "🔇 Talk mode off."
SETUP_BROKEN = (
    "⚠️ Talk mode couldn't start because the voice package isn't installed. Run: "
    r"C:\Users\olodh\Projects\claude-talk\.venv\Scripts\python.exe -m pip install -e C:\Users\olodh\Projects\claude-talk"
)
NUDGE = (
    "Talk mode is on: your reply will be read aloud to the user. Open with one or two plain sentences "
    "giving the gist, written the way you'd say it out loud. If the user is just chatting, keep the whole "
    "reply short and conversational. For technical work, put the details (code, file paths, lists) after "
    "the gist as usual; they stay on screen and won't be read out."
)


def tts_available() -> bool:
    return importlib.util.find_spec("edge_tts") is not None


def _block(reason: str) -> dict:
    return {"decision": "block", "reason": reason}


def handle_toggle(payload: dict) -> dict:
    session_id = payload.get("session_id") or ""
    if not switch.is_on(session_id) and not tts_available():
        return _block(SETUP_BROKEN)
    if switch.toggle(session_id, payload.get("prompt_id")):
        switch.cleanup_stale()  # the marker just set is brand new, so it is never swept
        return _block(TALK_ON)
    control.stop_speaking()
    return _block(TALK_OFF)


def handle_prompt(payload: dict) -> dict | None:
    prompt = next((payload[f] for f in PROMPT_FIELDS if isinstance(payload.get(f), str)), "").strip()
    if prompt.split(" ", 1)[0] == "/talk":
        return handle_toggle(payload)
    if payload.get("prompt_source", "user_input") == "user_input":
        control.stop_speaking()
    session_id = payload.get("session_id") or ""
    if switch.is_on(session_id):
        switch.turn_on(session_id)  # keeps an active session's marker from looking stale
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": NUDGE}}
    return None


def handle_stop(payload: dict) -> None:
    session_id = payload.get("session_id") or ""
    reply = (payload.get("last_assistant_message") or "").strip()
    if payload.get("agent_id") or not reply or not switch.is_on(session_id):
        return None
    cfg = load_config()
    speech = to_speech(reply, cfg.full_read_max_words, cfg.gist_max_words)
    pid = control.start_speaking(speech, session_id)
    get_logger().info("session %s: speaking %d words", session_id[:8], len(speech.split()))
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
        get_logger().exception("hook %s failed", argv[:1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
