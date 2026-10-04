# Claude Talk Speech Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let each Claude Code session choose how much of a reply Claude Talk reads aloud: `gist` (today), `full` (everything speakable) or `summary` (a 🔊 paragraph Claude writes at the end of the reply).

**Architecture:** `config.json` gains a default `mode`. Each session's marker file can hold a mode chosen with `/talk <mode>`. The hooks read the `/talk` argument, send a per-mode nudge, and pick the speech function in the Stop hook. `speakable` gains two pure functions, `full_speech` and `summary_speech`, built on its existing paragraph and cleanup helpers.

**Tech Stack:** Python 3.13 (project `.venv`), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-04-talk-modes-design.md`. It builds on the main spec, `docs/superpowers/specs/2026-10-04-claude-talk-design.md`.

## Global Constraints

- Windows only. Run everything from the project folder in PowerShell or Git Bash with the project venv: `.venv\Scripts\python.exe -m pytest` (Git Bash: `.venv/Scripts/python.exe -m pytest`).
- The three mode words are exactly `gist`, `full` and `summary`. The default is `gist`.
- Every hook exits 0 and never writes to stderr. Stdout carries only ASCII JSON (`json.dumps` default `ensure_ascii=True`).
- No new runtime or dev dependencies.
- Exact user-facing strings (spec §5):
  - `🔊 Talk mode on (<mode>): <description>. Tap Space or Esc to stop it talking.`
  - Descriptions:
    - gist: `Claude will read the gist of each reply aloud`
    - full: `Claude will read whole replies aloud, except code`
    - summary: `Claude will read a short spoken summary of each reply`
  - `🔇 Talk mode off.` (unchanged)
  - `⚠️ Unknown talk mode "<word>". Use /talk, /talk gist, /talk full or /talk summary.`
- Nudge texts are verbatim from spec §7.
- The `/talk` command file description reads `Turn reading replies aloud on or off, or pick a mode: gist, full or summary`, with `argument-hint: [gist|full|summary]`.
- Tests get an isolated Claude Talk home automatically (`tests/conftest.py` sets `CLAUDE_TALK_HOME` to `tmp_path`), so `paths.sessions_dir()`, `config.json` and `logs/talk.log` are per test.

## Review Focus

1. **🔊 in running text**, for example "I added a 🔊 icon": this must not be taken as the summary. Only a paragraph that starts with 🔊 counts. Test added in Task 2.
2. **Replies with Windows line endings (`\r\n`)**: the 🔊 paragraph must still be found. Test added in Task 2.
3. **`/talk` typed with odd spacing or capitals**, for example `/talk   SUMMARY`: this must still select summary mode. Test added in Task 4.
4. **A 🔊 paragraph with nothing after the emoji**: it must fall back to gist, not speak nothing. Tests added in Tasks 2 and 4.
5. **A session switched on before this change** (empty marker file): it must keep working and follow the default mode. Tests added in Tasks 3 and 4.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `talk/config.py` | `MODES` and the `mode` setting, with value checking | 1 |
| `config.json` | Shipped default `"mode": "gist"` | 1 |
| `talk/speakable.py` | `full_speech`, `summary_speech` | 2 |
| `talk/switch.py` | `turn_on(session_id, mode=None)`, `mode(session_id)` | 3 |
| `talk/hooks.py` | `/talk <mode>` handling, per-mode messages and nudges, speech choice in Stop | 4 |
| `talk/install.py` | `/talk` command description and `argument-hint` | 5 |
| `README.md`, both specs | Documentation | 6 |

---

### Task 1: `mode` setting in config

**Files:**
- Modify: `talk/config.py`
- Modify: `config.json`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `talk.config.MODES: tuple[str, ...] = ("gist", "full", "summary")` and `Config.mode: str` (default `"gist"`).

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_config.py`:

```python
def test_mode_defaults_to_gist():
    assert Config().mode == "gist"


def test_mode_can_be_chosen(talk_home):
    write_config(talk_home, json.dumps({"mode": "summary"}))
    assert load_config().mode == "summary"


def test_unknown_mode_falls_back_to_gist_and_is_logged(talk_home):
    write_config(talk_home, json.dumps({"mode": "loud", "voice": "en-GB-RyanNeural"}))
    cfg = load_config()
    assert cfg.mode == "gist"
    assert cfg.voice == "en-GB-RyanNeural"  # other keys still apply
    assert "mode='loud'" in (talk_home / "logs" / "talk.log").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run them to see them fail.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py -q`
Expected: 3 failures, with `AttributeError: 'Config' object has no attribute 'mode'` (or `TypeError` on the unexpected key).

- [ ] **Step 3: Implement.** In `talk/config.py`, add `MODES` above the dataclass, add the field, and check the value in `load_config`:

```python
MODES = ("gist", "full", "summary")


@dataclass(frozen=True)
class Config:
    voice: str = "en-GB-SoniaNeural"
    rate: str = "+0%"
    full_read_max_words: int = 120
    gist_max_words: int = 60
    closing_max_words: int = 40
    fallback_to_windows_voice: bool = True
    mode: str = "gist"
```

Replace the body of the `for field in fields(Config):` loop with:

```python
    for field in fields(Config):
        if field.name not in data:
            continue
        value, default = data[field.name], getattr(defaults, field.name)
        if type(value) is not type(default):
            get_logger().warning(
                "Ignoring config.json %s=%r: expected %s", field.name, value, type(default).__name__
            )
        elif field.name == "mode" and value not in MODES:
            get_logger().warning("Ignoring config.json mode=%r: expected one of %s", value, ", ".join(MODES))
        else:
            values[field.name] = value
```

In `config.json`, add `"mode": "gist"` as the last key:

```json
{
  "voice": "en-GB-SoniaNeural",
  "rate": "+0%",
  "full_read_max_words": 120,
  "gist_max_words": 60,
  "closing_max_words": 40,
  "fallback_to_windows_voice": true,
  "mode": "gist"
}
```

- [ ] **Step 4: Run the config tests, then the full suite.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py -q`, then `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass. The full suite has 2 skipped, the online tests.

- [ ] **Step 5: Commit.**

```bash
git add talk/config.py config.json tests/test_config.py
git commit -m "feat: add the default speech mode setting"
```

---

### Task 2: `full_speech` and `summary_speech`

**Files:**
- Modify: `talk/speakable.py`
- Test: `tests/test_speakable.py`

**Interfaces:**
- Consumes: existing private helpers in `talk/speakable.py`: `_paragraphs(markdown) -> list[tuple[str, bool]]`, `_clean_inline(line) -> str`, `_end_sentence(text) -> str`, `_FENCE`, `NOTHING_TO_SAY`.
- Produces:
  - `full_speech(markdown: str) -> str`: every speakable paragraph joined in order, or `NOTHING_TO_SAY`.
  - `summary_speech(markdown: str) -> str | None`: the cleaned text of the last paragraph that starts with 🔊, or `None`.

- [ ] **Step 1: Write the failing tests.** In `tests/test_speakable.py`, change the import line to:

```python
from talk.speakable import (
    DETAILS_ON_SCREEN, NOTHING_TO_SAY, REST_ON_SCREEN, full_speech, speech_chunks, split_sentences, summary_speech,
    to_speech,
)
```

Append:

```python
LONG_PROSE = " ".join([TEN_WORDS] * 15)  # one 150-word paragraph, over the 120-word full-read limit


def test_full_speech_reads_past_the_length_limits():
    reply = f"Opening line here.\n\n{LONG_PROSE}\n\nWant me to carry on?"
    assert full_speech(reply) == f"Opening line here. {LONG_PROSE} Want me to carry on?"


def test_full_speech_still_skips_code_blocks_and_tables():
    reply = "Before the code.\n\n```py\nprint(1)\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nAfter the table."
    assert full_speech(reply) == "Before the code. After the table."


def test_full_speech_reads_list_items_as_sentences():
    assert full_speech("Steps:\n\n- one\n- two\n\nDone") == "Steps: one. two. Done."


def test_full_speech_of_a_code_only_reply():
    assert full_speech("```py\nprint(1)\n```") == NOTHING_TO_SAY


def test_summary_is_the_last_speaker_paragraph():
    reply = "Screen text.\n\n🔊 An earlier summary.\n\nMore text.\n\n🔊 The fix is in. Shall I push it?"
    assert summary_speech(reply) == "The fix is in. Shall I push it?"


def test_summary_wrapped_over_two_lines_is_kept_whole():
    reply = "Body text.\n\n🔊 The fix is in and tested.\nShall I push it?\n\nTrailing note."
    assert summary_speech(reply) == "The fix is in and tested. Shall I push it?"


def test_summary_is_cleaned_like_other_speech():
    reply = "Body.\n\n🔊 I changed `src/auth/session.ts:42` and **all** tests pass"
    assert summary_speech(reply) == "I changed session.ts and all tests pass."


def test_summary_may_be_indented_or_use_the_emoji_variation_selector():
    assert summary_speech("Body.\n\n  🔊️ Done.") == "Done."


def test_summary_inside_a_code_block_is_ignored():
    assert summary_speech("Body.\n\n```text\n🔊 not this\n```\n") is None


def test_speaker_emoji_in_running_text_is_not_a_summary():
    assert summary_speech("I added a 🔊 icon to the toolbar.") is None


def test_summary_found_in_a_reply_with_windows_line_endings():
    assert summary_speech("Body.\r\n\r\n🔊 Short version.\r\n") == "Short version."


def test_no_summary_or_an_empty_one():
    assert summary_speech("Just a normal reply.") is None
    assert summary_speech("Body.\n\n🔊") is None
```

- [ ] **Step 2: Run them to see them fail.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_speakable.py -q`
Expected: collection error `ImportError: cannot import name 'full_speech'`.

- [ ] **Step 3: Implement.** In `talk/speakable.py`, add this pattern beside the other module-level patterns, after `_SENTENCE_BREAK`:

```python
_SUMMARY_START = re.compile("^\\s*\U0001F50A️?")
```

Add these two functions directly after `to_speech`:

```python
def full_speech(markdown: str) -> str:
    """Every speakable paragraph, in order, with no length limit (same cleanup as to_speech)."""
    texts = [text for text, _ in _paragraphs(markdown)]
    return " ".join(texts) if texts else NOTHING_TO_SAY


def summary_speech(markdown: str) -> str | None:
    """The spoken summary Claude writes in summary mode: the last paragraph starting with 🔊 (code blocks
    ignored), cleaned for speech. None when there is no such paragraph or it is empty."""
    text = _FENCE.sub("\n", markdown.replace("\r\n", "\n"))
    found: list[str] | None = None
    current: list[str] | None = None
    for line in text.split("\n"):
        if current is not None:
            if line.strip():
                current.append(line)
                continue
            found, current = current, None
        if _SUMMARY_START.match(line):
            current = [_SUMMARY_START.sub("", line, count=1)]
    if current is not None:
        found = current
    if found is None:
        return None
    spoken = _clean_inline(" ".join(found))
    return _end_sentence(spoken) if spoken else None
```

- [ ] **Step 4: Run the speakable tests, then the full suite.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_speakable.py -q`, then `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add talk/speakable.py tests/test_speakable.py
git commit -m "feat: add full and summary speech"
```

---

### Task 3: Per-session mode in the switch

**Files:**
- Modify: `talk/switch.py`
- Test: `tests/test_switch.py`

**Interfaces:**
- Consumes: `talk.config.MODES` (Task 1).
- Produces:
  - `switch.turn_on(session_id: str, mode: str | None = None) -> None`: stores `mode` when given, and otherwise keeps the marker's contents (creating an empty marker if there wasn't one).
  - `switch.mode(session_id: str) -> str | None`: the stored mode, or `None` for "use the default". It returns `None` for unknown words, missing markers and bad ids, and never raises.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_switch.py`:

```python
def test_mode_is_stored_per_session():
    switch.turn_on("s1", "summary")
    switch.turn_on("s2")
    assert switch.mode("s1") == "summary"
    assert switch.mode("s2") is None  # plain /talk: follow the default


def test_refreshing_the_marker_keeps_the_mode():
    switch.turn_on("s1", "full")
    switch.turn_on("s1")
    assert switch.mode("s1") == "full"
    assert switch.is_on("s1") is True


def test_turning_off_forgets_the_mode():
    switch.turn_on("s1", "full")
    switch.turn_off("s1")
    switch.turn_on("s1")
    assert switch.mode("s1") is None


def test_marker_from_before_modes_existed_follows_the_default():
    (paths.sessions_dir() / "s1").touch()  # empty marker, as written by the previous version
    assert switch.is_on("s1") is True
    assert switch.mode("s1") is None


def test_unknown_word_in_a_marker_means_default():
    (paths.sessions_dir() / "s1").write_text("loud", encoding="utf-8")
    assert switch.mode("s1") is None


def test_mode_of_missing_or_bad_sessions_is_none():
    assert switch.mode("nobody") is None
    assert switch.mode("") is None
```

- [ ] **Step 2: Run them to see them fail.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_switch.py -q`
Expected: failures with `TypeError: turn_on() takes 1 positional argument but 2 were given` and `AttributeError: module 'talk.switch' has no attribute 'mode'`.

- [ ] **Step 3: Implement.** In `talk/switch.py`:
  - Update the module docstring.
  - Import `MODES`.
  - Replace `turn_on`.
  - Add `mode` after `is_on`.

```python
"""Per-session talk mode, stored as one marker file per session in state/sessions/.

A marker's existence means talk is on. Its contents are the mode chosen with /talk <mode>, or empty
to follow the default mode in config.json."""
import time
from pathlib import Path

from talk import paths
from talk.config import MODES
```

```python
def mode(session_id: str) -> str | None:
    """The mode chosen for this session, or None to use the default."""
    try:
        word = _marker(session_id).read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None
    return word if word in MODES else None


def turn_on(session_id: str, mode: str | None = None) -> None:
    """Switch talk on. A given mode is stored; otherwise the marker keeps its contents (touch refreshes its age)."""
    marker = _marker(session_id)
    if mode is None:
        marker.touch()
    else:
        marker.write_text(mode, encoding="utf-8")
```

- [ ] **Step 4: Run the switch tests, then the full suite.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_switch.py -q`, then `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add talk/switch.py tests/test_switch.py
git commit -m "feat: remember each session's speech mode"
```

---

### Task 4: Hooks — `/talk <mode>`, per-mode nudge, speech choice

**Files:**
- Modify: `talk/hooks.py`
- Test: `tests/test_hooks.py`

**Interfaces:**
- Consumes:
  - `talk.config.MODES` and `Config.mode` (Task 1).
  - `talk.speakable.full_speech` and `summary_speech` (Task 2).
  - `switch.turn_on(session_id, mode)` and `switch.mode(session_id)` (Task 3).
- Produces:
  - `hooks.talk_on_message(mode: str) -> str`
  - `hooks.unknown_mode_message(word: str) -> str`
  - `hooks.NUDGES: dict[str, str]`
  - `hooks.MODE_DESCRIPTIONS: dict[str, str]`
  - `hooks.TALK_ON` and `hooks.NUDGE` are removed. `TALK_OFF` is unchanged.

- [ ] **Step 1: Update the existing tests to the new names.** In `tests/test_hooks.py`:
  - Replace every `block(hooks.TALK_ON)` with `block(hooks.talk_on_message("gist"))`. There are 4: `test_toggle_turns_talk_mode_on`, twice in `test_same_talk_command_through_both_hooks_toggles_once`, and `test_user_prompt_field_name_also_works`.
  - In `test_output_is_ascii_json`, replace `hooks.TALK_ON` with `hooks.talk_on_message("gist")`.
  - In `test_prompt_in_talk_session_adds_the_nudge`, replace `hooks.NUDGE` with `hooks.NUDGES["gist"]`.

- [ ] **Step 2: Write the failing tests.** Append to `tests/test_hooks.py`:

```python
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
```

- [ ] **Step 3: Run them to see them fail.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_hooks.py -q`
Expected: many failures with `AttributeError: module 'talk.hooks' has no attribute 'talk_on_message'` (and `NUDGES`, `unknown_mode_message`).

- [ ] **Step 4: Implement.** In `talk/hooks.py`:

Change the imports:

```python
from talk import control, paths, procs, switch
from talk.config import MODES, Config, load_config
from talk.log import get_logger
from talk.speakable import full_speech, summary_speech, to_speech
```

Replace `TALK_ON = ...` and the whole `NUDGE = (...)` block (keep `TALK_OFF`) with:

```python
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
    return f'⚠️ Unknown talk mode "{word}". Use /talk, /talk gist, /talk full or /talk summary.'
```

Replace `handle_toggle`, `handle_prompt` and `handle_stop` with:

```python
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


def _speech_for(reply: str, mode: str, cfg: Config) -> str:
    if mode == "full":
        return full_speech(reply)
    if mode == "summary":
        summary = summary_speech(reply)
        if summary:
            return summary
        get_logger().info("no spoken summary; using gist")
    return to_speech(reply, cfg.full_read_max_words, cfg.gist_max_words, cfg.closing_max_words)


def handle_stop(payload: dict) -> None:
    session_id = payload.get("session_id") or ""
    reply = (payload.get("last_assistant_message") or "").strip()
    if payload.get("agent_id") or not reply or not switch.is_on(session_id):
        return None
    cfg = load_config()
    mode = _session_mode(session_id, cfg)
    speech = _speech_for(reply, mode, cfg)
    pid = control.start_speaking(speech, session_id)
    get_logger().info("session %s: speaking %d words (%s)", session_id[:8], len(speech.split()), mode)
    if WAIT_FOR_SPEAKER:
        while procs.is_alive(pid):
            time.sleep(0.2)
    return None
```

- [ ] **Step 5: Run the hook tests, then the full suite.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_hooks.py tests/test_hooks_process.py -q`, then `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass. `test_bad_input_never_fails` must still pass: an empty `session_id` with `command_args` raises `ValueError` inside `switch.turn_on`, which `main` catches and logs.

- [ ] **Step 6: Commit.**

```bash
git add talk/hooks.py tests/test_hooks.py
git commit -m "feat: choose gist, full or summary speech per session with /talk <mode>"
```

---

### Task 5: `/talk` command file shows the modes

**Files:**
- Modify: `talk/install.py`
- Test: `tests/test_install.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `install.command_md()` frontmatter with the new description and `argument-hint: [gist|full|summary]`.

- [ ] **Step 1: Write the failing test.** Append to `tests/test_install.py`:

```python
def test_command_offers_the_modes():
    frontmatter = install.command_md().split("---")[1]
    assert "argument-hint: [gist|full|summary]" in frontmatter
    assert "description: Turn reading replies aloud on or off, or pick a mode: gist, full or summary" in frontmatter
```

- [ ] **Step 2: Run it to see it fail.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_install.py -q`
Expected: 1 failure, `test_command_offers_the_modes`.

- [ ] **Step 3: Implement.** In `talk/install.py`, change the frontmatter in `command_md()`:

```python
def command_md() -> str:
    return f"""---
description: Turn reading replies aloud on or off, or pick a mode: gist, full or summary
argument-hint: [gist|full|summary]
disable-model-invocation: true
---
Reply with exactly this sentence and nothing else: "Talk mode isn't set up correctly. Check {paths.root() / 'logs' / 'talk.log'}."
"""
```

- [ ] **Step 4: Run the install tests, then the full suite.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_install.py -q`, then `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add talk/install.py tests/test_install.py
git commit -m "feat: show the speech modes in /talk autocomplete"
```

---

### Task 6: Docs, local reinstall, full verification

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-10-04-claude-talk-design.md`
- Modify: `docs/superpowers/specs/2026-10-04-talk-modes-design.md`

- [ ] **Step 1: README.** Replace the "Use it" list with:

```markdown
1. In any Claude Code session, type `/talk`. You'll see "🔊 Talk mode on (gist)".
2. Tap **Space**, speak, then tap **Space** again to send (built-in tap dictation).
3. Claude replies on screen and reads part of it aloud, depending on the mode (below). Code stays on screen.
4. Tap **Space** (to reply) or press **Esc** to cut Claude off.
5. Type `/talk` again to turn it off. Other sessions stay silent unless you turn them on.

### Modes

| Type | What Claude reads aloud |
|---|---|
| `/talk gist` | The opening, then "The remainder of details are on screen." and the closing question or offer |
| `/talk full` | The whole reply, except code blocks and tables |
| `/talk summary` | A short spoken summary that Claude adds as the last line of its reply, starting with 🔊 |

`/talk` on its own uses the `mode` setting (default `gist`). Typing a mode while talk is on switches mode without turning it off. In summary mode, if Claude forgets the 🔊 line, the gist is read instead.
```

Add this row to the Settings table, after `voice`:

```markdown
| `mode` | `gist` | Mode used by `/talk` on its own: `gist`, `full` or `summary` |
```

- [ ] **Step 2: Main spec.** In `docs/superpowers/specs/2026-10-04-claude-talk-design.md`:
  - **§7.1:** change the on-message sentence to: "If the marker is absent, it's created and the reply is "🔊 Talk mode on (<mode>): …" (see the speech modes spec for `/talk <mode>`)."
  - **§7.2:** after the quoted nudge, add: "That is the gist-mode nudge; full and summary modes have their own (speech modes spec §7)."
  - **§7.4:** after the heading, add: "This is gist mode, the default. Full and summary modes are described in `2026-10-04-talk-modes-design.md`."
  - **§8:** add `"mode": "gist"` to the JSON block.
  - **§13:** add the bullet: "**Speech modes**: `/talk gist|full|summary`, a `mode` default in `config.json`, and a 🔊 summary line in summary mode (`2026-10-04-talk-modes-design.md`)."

- [ ] **Step 3: Modes spec status.** In `docs/superpowers/specs/2026-10-04-talk-modes-design.md`, change `**Status:** Approved in conversation, awaiting written review` to `**Status:** Implemented`.

- [ ] **Step 4: Full suite including online tests.**

Run (Git Bash): `TALK_NETWORK_TESTS=1 .venv/Scripts/python.exe -m pytest -q`
Expected: all pass, 0 skipped.

- [ ] **Step 5: Refresh this PC's install** so `~/.claude/commands/talk.md` gets the new hint. The installer backs up `settings.json` first.

Run: `.venv\Scripts\python.exe -P -m talk.install`
Expected: "Claude Talk installed: …". Check that `~\.claude\commands\talk.md` contains `argument-hint: [gist|full|summary]`.

- [ ] **Step 6: Commit.**

```bash
git add README.md docs/superpowers/specs/2026-10-04-claude-talk-design.md docs/superpowers/specs/2026-10-04-talk-modes-design.md
git commit -m "docs: describe the speech modes"
```

- [ ] **Step 7: Manual check with Omar** (spec §11), in a new Claude Code session:
  1. `/talk full`: a long reply is read to the end.
  2. `/talk summary`: only the 🔊 line is read.
  3. `/talk gist`: today's behaviour.
  4. `/talk sumary`: the warning appears.
  5. `/talk`: talk turns off.

- [ ] **Step 8: Merge and push**, only after Omar is happy with the manual check:

```bash
git switch main
git merge --ff-only talk-modes
git branch -d talk-modes
git push origin main
```
