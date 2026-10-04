# Claude Talk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Claude Code read its replies aloud, in Microsoft's neural voices, in sessions where the user has typed `/talk`.

**Architecture:** A small Python package (`talk`) registered as Claude Code hooks. `/talk` flips a per-session marker file. A `UserPromptSubmit` hook adds a "this will be read aloud" nudge to talk sessions. A `Stop` hook turns the reply into speakable text and launches a detached speaker process. The speaker synthesises sentence by sentence with `edge-tts`, plays MP3s through the Windows MCI API, and stops on Space/Esc, on a stop request or when a newer reply takes over. It falls back to the Windows built-in voice if the online voice fails.

**Tech Stack:** Python 3.13 (project venv), `edge-tts` 7.2.x, `pytest`, Windows APIs via `ctypes` (winmm, user32, kernel32), PowerShell `System.Speech` for the fallback voice.

**Spec:** `docs/superpowers/specs/2026-10-04-claude-talk-design.md`

## Global Constraints

- Windows 11 only. Python 3.13 in `C:\Users\olodh\Projects\claude-talk\.venv`. The only runtime dependency is `edge-tts>=7.2,<8`; the only dev dependency is `pytest>=8`.
- Run every command from `C:\Users\olodh\Projects\claude-talk` in PowerShell. Tests run with `.venv\Scripts\python.exe -m pytest`.
- Hooks are registered in **exec form** (`command` = absolute path to `.venv\Scripts\python.exe`, `args` = `["-m", "talk.hooks", "<event>"]`), so no shell quoting is involved.
- Every hook exits 0 and never writes to stderr. Stdout carries only ASCII JSON (`json.dumps` default `ensure_ascii=True`) for the `/talk` message and the nudge.
- Default config: `voice` `en-GB-SoniaNeural`, `rate` `+0%`, `full_read_max_words` 120, `gist_max_words` 60, `fallback_to_windows_voice` true.
- Exact user-facing strings:
  - `🔊 Talk mode on: Claude will read replies aloud. Tap Space or Esc to stop it talking.`
  - `🔇 Talk mode off.`
  - `The rest is on screen.`
  - `Done. The details are on screen.`
- Nudge text (verbatim): `Talk mode is on: your reply will be read aloud to the user. Open with one or two plain sentences giving the gist, written the way you'd say it out loud. If the user is just chatting, keep the whole reply short and conversational. For technical work, put the details (code, file paths, lists) after the gist as usual; they stay on screen and won't be read out.`
- Inline code is spoken only if it is 3 words or fewer and 30 characters or fewer.
- Timings: first audio within 5 s or fall back; later chunks within 15 s or fall back; stop/key polling every 50 ms; a stop waits 500 ms, then force-kills.
- Stale session markers are removed after 7 days. Log: `logs/talk.log`, 1 MB, 1 backup.
- `state/`, `logs/`, `.venv/` and `probe/` are never committed. `CLAUDE_TALK_HOME` overrides the project root (tests only).
- Every commit ends with the two trailers, written as:
  `git commit -m "<message>" --trailer "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" --trailer "Claude-Session: https://claude.ai/code/session_01PynKPRx4DNyfD6UkLUSyJL"`

## Review Focus

1. **Non-ASCII text on a Windows console.** Emoji in `/talk` messages, and `£` or curly quotes in replies, must not crash a hook, even when stdin/stdout use cp1252. Pinned in Task 8 (`test_output_is_ascii_json`, `test_stop_handles_non_ascii_reply`).
2. **The user replies while the speaker is still fetching its first audio.** It must go quiet without ever starting to talk. Pinned in Task 6 (`test_stop_while_waiting_for_first_audio`).
3. **Space is still held, or being typed, at the moment speech starts.** It must not cut speech off instantly; only a fresh press counts. Pinned in Task 6 (`test_key_held_at_start_only_counts_after_release`).
4. **Leftovers from a crashed or killed speaker** (`speaker.json` naming a dead process, old temp folders and job files). The next reply must speak normally. Pinned in Task 5 (`test_stale_record_with_dead_pid_is_cleared`) and Task 7 (`test_sweep_removes_only_old_leftovers`).
5. **A hand-edited `config.json`** (Notepad BOM, wrong value types, broken JSON) or **a hook payload with missing fields**. Both must fall back to defaults with no crash. Pinned in Task 2 (`test_config_with_bom_loads`, `test_wrong_types_fall_back_per_key`) and Task 8 (`test_bad_input_never_fails`).

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, dependencies, pytest config |
| `config.json` | User-editable voice and length settings |
| `talk/__init__.py` | Package marker |
| `talk/paths.py` | Where state, jobs, logs and config live (`CLAUDE_TALK_HOME` override) |
| `talk/log.py` | One rotating log file; never writes to stderr |
| `talk/config.py` | `Config` dataclass + `load_config()` with per-key fallback |
| `talk/speakable.py` | Pure text rules: Markdown reply → spoken text; sentence chunking |
| `talk/switch.py` | Per-session on/off markers, de-duplicated toggle, stale cleanup |
| `talk/procs.py` | Windows process helpers: detached spawn, alive check, tree kill |
| `talk/control.py` | One-speaker-at-a-time registry: start, stop, should_stop, clear |
| `talk/keys.py` | Fresh Space/Esc press detection (`GetAsyncKeyState`) |
| `talk/playback.py` | MP3/WAV playback via Windows MCI |
| `talk/tts.py` | `edge-tts` synthesis + Windows built-in voice fallback |
| `talk/speaker.py` | Speaker process: orchestrates synth → play → stop/fallback |
| `talk/hooks.py` | Hook entry points (`prompt`, `toggle`, `stop`, `session-end`) |
| `talk/install.py` | Merge hooks into `~/.claude/settings.json`, write `/talk` command, uninstall |
| `scripts/say.py` | Manual smoke test: speak a sentence through the real pipeline |
| `tests/…` | One test file per module; `tests/fake_speaker.py` stands in for the speaker |
| `README.md` | Setup and usage |

---

### Task 1: Probe how the hooks behave (spike)

Confirms the assumptions the design relies on before any product code is written. Nothing from this task ships except the findings note.

**Files:**
- Create: `probe/probe_hook.py`, `probe/probe-settings.json`, `probe/.claude/commands/talk.md` (all throwaway, gitignored)
- Create: `docs/superpowers/notes/2026-10-04-hook-probe.md` (committed)
- Modify: `.gitignore` (add `probe/`)

**Interfaces:**
- Produces: two decisions recorded in the findings note, used by Task 8:
  - `PROMPT_FIELDS`, the name(s) of the prompt text field in `UserPromptSubmit` input
  - `WAIT_FOR_SPEAKER`, normally `False`

- [ ] **Step 1: Add `probe/` to `.gitignore`**

Append this line to `.gitignore`:

```
probe/
```

- [ ] **Step 2: Find the Python launcher path**

Run: `(Get-Command py).Source`
Expected: `C:\Windows\py.exe`. Use the printed path wherever `C:\\Windows\\py.exe` appears below if it differs.

- [ ] **Step 3: Write the probe hook**

Create `probe/probe_hook.py`:

```python
"""Throwaway probe: logs every hook payload and tests blocking and detached children."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
event = sys.argv[1]
raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
with (HERE / "log.jsonl").open("a", encoding="utf-8") as log:
    log.write(json.dumps({"event": event, "time": time.time(), "payload": raw}) + "\n")

mode = os.environ.get("PROBE_MODE", "")
if event == "UserPromptSubmit" and mode == "block-submit" and "/talk" in raw:
    print(json.dumps({"decision": "block", "reason": "probe: blocked in UserPromptSubmit"}))
elif event == "UserPromptExpansion":
    print(json.dumps({"decision": "block", "reason": "probe: blocked in UserPromptExpansion"}))
elif event == "Stop":
    marker = HERE / "child_survived.txt"
    marker.unlink(missing_ok=True)
    child = [sys.executable, "-c", f"import time, pathlib; time.sleep(5); pathlib.Path(r'{marker}').write_text('yes')"]
    base = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(child, creationflags=base | 0x01000000,  # | CREATE_BREAKAWAY_FROM_JOB
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        how = "breakaway"
    except OSError:
        subprocess.Popen(child, creationflags=base,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        how = "no-breakaway"
    with (HERE / "log.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps({"event": "Stop-child", "spawned": how}) + "\n")
```

- [ ] **Step 4: Write the probe settings and command**

Create `probe/probe-settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {"hooks": [{"type": "command", "command": "C:\\Windows\\py.exe", "args": ["-3.13", "C:\\Users\\olodh\\Projects\\claude-talk\\probe\\probe_hook.py", "UserPromptSubmit"]}]}
    ],
    "UserPromptExpansion": [
      {"matcher": "talk", "hooks": [{"type": "command", "command": "C:\\Windows\\py.exe", "args": ["-3.13", "C:\\Users\\olodh\\Projects\\claude-talk\\probe\\probe_hook.py", "UserPromptExpansion"]}]}
    ],
    "Stop": [
      {"hooks": [{"type": "command", "command": "C:\\Windows\\py.exe", "args": ["-3.13", "C:\\Users\\olodh\\Projects\\claude-talk\\probe\\probe_hook.py", "Stop"], "async": true}]}
    ],
    "SessionEnd": [
      {"hooks": [{"type": "command", "command": "C:\\Windows\\py.exe", "args": ["-3.13", "C:\\Users\\olodh\\Projects\\claude-talk\\probe\\probe_hook.py", "SessionEnd"]}]}
    ]
  }
}
```

Create `probe/.claude/commands/talk.md`:

```markdown
---
description: probe command
---
Reply with exactly: PROBE-EXPANDED
```

- [ ] **Step 5: Run probe A (expansion blocking)**

```powershell
Set-Location C:\Users\olodh\Projects\claude-talk\probe
Remove-Item Env:CLAUDECODE -ErrorAction SilentlyContinue
$env:PROBE_MODE = ""
claude -p "/talk" --settings probe-settings.json --model haiku
```

Note what `claude` printed. `PROBE-EXPANDED` means `/talk` reached the model, i.e. it was not blocked.

- [ ] **Step 6: Run probe B (`UserPromptSubmit` blocking)**

```powershell
$env:PROBE_MODE = "block-submit"
claude -p "/talk" --settings probe-settings.json --model haiku
```

- [ ] **Step 7: Run probe C (Stop payload and detached child survival)**

```powershell
$env:PROBE_MODE = ""
claude -p "Reply with the single word pong." --settings probe-settings.json --model haiku
Start-Sleep -Seconds 8
Test-Path .\child_survived.txt
Get-Content .\log.jsonl
Set-Location C:\Users\olodh\Projects\claude-talk
```

- [ ] **Step 8: Write the findings note**

Create `docs/superpowers/notes/2026-10-04-hook-probe.md`, answering each question from `probe/log.jsonl` and the console output. Paste the relevant payload JSON under each one.

```markdown
# Hook probe findings (2026-10-04, Claude Code <version from `claude --version`>)

Q1. In UserPromptSubmit, which field holds the typed text, and is it the raw "/talk"? → ...
Q2. When UserPromptSubmit blocked "/talk" (probe B), did UserPromptExpansion still fire? → ...
Q3. Did UserPromptExpansion fire for "/talk" with matcher "talk", and did its block stop the model (probe A)? Field names? Is prompt_id present in both events? → ...
Q4. Does the Stop payload include last_assistant_message? → ...
Q5. Did the detached child survive (child_survived.txt exists)? Spawned with breakaway or not? → ...
Q6. Did SessionEnd fire in -p mode, and with which fields? → ...

Decisions:
- PROMPT_FIELDS = (...)
- WAIT_FOR_SPEAKER = False (or: "re-check in Task 10", if Q5 failed in -p mode)
```

**Decision rules:**
- Q1 field name not `prompt` or `user_prompt`: add it to `PROMPT_FIELDS` in Task 8.
- Neither probe A nor probe B blocked `/talk` (both printed `PROBE-EXPANDED`): **stop and report to Omar.** The toggle design needs rethinking.
- Q4 says there's no `last_assistant_message`: **stop and report to Omar.** The speaker would need to read the transcript instead.
- Q5 failed: keep `WAIT_FOR_SPEAKER = False` for now. In `-p` mode the whole CLI exits after the turn, so this is inconclusive. Task 10 re-checks it in an interactive session.
- prompt_id missing from either event: note it. `switch.toggle` still works, but without de-duplication.

- [ ] **Step 9: Commit**

```powershell
git add .gitignore docs/superpowers/notes/2026-10-04-hook-probe.md
git commit -m "docs: record hook probe findings" --trailer "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" --trailer "Claude-Session: https://claude.ai/code/session_01PynKPRx4DNyfD6UkLUSyJL"
```

---

### Task 2: Project scaffold, paths, logging and config

**Files:**
- Create: `pyproject.toml`, `config.json`, `talk/__init__.py`, `talk/paths.py`, `talk/log.py`, `talk/config.py`
- Test: `tests/conftest.py`, `tests/test_paths.py`, `tests/test_log.py`, `tests/test_config.py`

**Interfaces:**
- Produces:
  - `talk.paths.root() -> Path`, `state_dir() -> Path`, `sessions_dir() -> Path`, `jobs_dir() -> Path` (all created on call), `log_file() -> Path` (parent created), `config_file() -> Path`
  - `talk.log.get_logger() -> logging.Logger`
  - `talk.config.Config` (frozen dataclass: `voice: str`, `rate: str`, `full_read_max_words: int`, `gist_max_words: int`, `fallback_to_windows_voice: bool`), `talk.config.load_config() -> Config`
  - pytest fixture `talk_home` (autouse): a fresh `CLAUDE_TALK_HOME` per test

- [ ] **Step 1: Create the package files and venv**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "claude-talk"
version = "0.1.0"
description = "Makes Claude Code read its replies aloud"
requires-python = ">=3.13"
dependencies = ["edge-tts>=7.2,<8"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.setuptools]
packages = ["talk"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Create `talk/__init__.py`:

```python
"""Claude Talk: makes Claude Code read its replies aloud."""
```

Create `config.json`:

```json
{
  "voice": "en-GB-SoniaNeural",
  "rate": "+0%",
  "full_read_max_words": 120,
  "gist_max_words": 60,
  "fallback_to_windows_voice": true
}
```

Run:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Expected: ends with `Successfully installed ... claude-talk-0.1.0 ... edge-tts-7.2.x ... pytest-...`

- [ ] **Step 2: Write the failing tests**

Create `tests/conftest.py`:

```python
import pytest


@pytest.fixture(autouse=True)
def talk_home(tmp_path, monkeypatch):
    """Every test gets its own empty Claude Talk home (state, logs, config)."""
    monkeypatch.setenv("CLAUDE_TALK_HOME", str(tmp_path))
    return tmp_path
```

Create `tests/test_paths.py`:

```python
from pathlib import Path

from talk import paths


def test_everything_lives_under_home(talk_home):
    assert paths.root() == talk_home
    assert paths.state_dir() == talk_home / "state"
    assert paths.sessions_dir() == talk_home / "state" / "sessions"
    assert paths.jobs_dir() == talk_home / "state" / "jobs"
    assert paths.log_file() == talk_home / "logs" / "talk.log"
    assert paths.config_file() == talk_home / "config.json"


def test_directories_are_created(talk_home):
    assert paths.sessions_dir().is_dir()
    assert paths.jobs_dir().is_dir()
    assert paths.log_file().parent.is_dir()


def test_default_root_is_the_project_folder(monkeypatch):
    monkeypatch.delenv("CLAUDE_TALK_HOME")
    assert paths.root() == Path(paths.__file__).resolve().parent.parent
```

Create `tests/test_log.py`:

```python
from talk.log import get_logger


def test_writes_to_log_file_under_home(talk_home):
    get_logger().info("hello from the test")
    assert "hello from the test" in (talk_home / "logs" / "talk.log").read_text(encoding="utf-8")


def test_follows_a_change_of_home(tmp_path, monkeypatch):
    get_logger().info("first")
    other = tmp_path / "other"
    monkeypatch.setenv("CLAUDE_TALK_HOME", str(other))
    get_logger().info("second")
    assert "second" in (other / "logs" / "talk.log").read_text(encoding="utf-8")
    assert len(get_logger().handlers) == 1


def test_log_is_capped_at_one_megabyte_with_one_backup():
    handler = get_logger().handlers[0]
    assert handler.maxBytes == 1_000_000
    assert handler.backupCount == 1
```

Create `tests/test_config.py`:

```python
import json

from talk.config import Config, load_config


def write_config(talk_home, text, encoding="utf-8"):
    (talk_home / "config.json").write_text(text, encoding=encoding)


def test_missing_file_gives_defaults():
    assert load_config() == Config()
    assert Config().voice == "en-GB-SoniaNeural"
    assert Config().rate == "+0%"
    assert Config().full_read_max_words == 120
    assert Config().gist_max_words == 60
    assert Config().fallback_to_windows_voice is True


def test_values_override_defaults_per_key(talk_home):
    write_config(talk_home, json.dumps({"voice": "en-GB-RyanNeural", "gist_max_words": 40}))
    cfg = load_config()
    assert cfg.voice == "en-GB-RyanNeural"
    assert cfg.gist_max_words == 40
    assert cfg.rate == "+0%"


def test_broken_json_gives_defaults_and_is_logged(talk_home):
    write_config(talk_home, "{ not json")
    assert load_config() == Config()
    assert "Ignoring unreadable config.json" in (talk_home / "logs" / "talk.log").read_text(encoding="utf-8")


def test_non_object_json_gives_defaults(talk_home):
    write_config(talk_home, "[1, 2]")
    assert load_config() == Config()


def test_wrong_types_fall_back_per_key(talk_home):
    write_config(talk_home, json.dumps({"gist_max_words": "sixty", "full_read_max_words": True, "voice": "en-GB-RyanNeural"}))
    cfg = load_config()
    assert cfg.gist_max_words == 60
    assert cfg.full_read_max_words == 120
    assert cfg.voice == "en-GB-RyanNeural"


def test_config_with_bom_loads(talk_home):
    write_config(talk_home, json.dumps({"rate": "+10%"}), encoding="utf-8-sig")
    assert load_config().rate == "+10%"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paths.py tests/test_log.py tests/test_config.py -v`
Expected: FAIL / errors with `ImportError: cannot import name 'paths' from 'talk'` (and similarly for `talk.log` and `talk.config`)

- [ ] **Step 4: Write the implementation**

Create `talk/paths.py`:

```python
"""Where Claude Talk keeps its files. CLAUDE_TALK_HOME overrides the project folder (used by tests)."""
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def root() -> Path:
    return Path(os.environ.get("CLAUDE_TALK_HOME", _PROJECT_ROOT))


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_dir() -> Path:
    return _ensure(root() / "state")


def sessions_dir() -> Path:
    return _ensure(state_dir() / "sessions")


def jobs_dir() -> Path:
    return _ensure(state_dir() / "jobs")


def log_file() -> Path:
    return _ensure(root() / "logs") / "talk.log"


def config_file() -> Path:
    return root() / "config.json"
```

Create `talk/log.py`:

```python
"""One rotating log file shared by every Claude Talk process. Logging never writes to stderr."""
import logging
import os
from logging.handlers import RotatingFileHandler

from talk import paths

logging.raiseExceptions = False  # a logging failure must never print to stderr inside a hook


def get_logger() -> logging.Logger:
    logger = logging.getLogger("claude_talk")
    target = os.path.abspath(paths.log_file())
    if not any(getattr(handler, "baseFilename", None) == target for handler in logger.handlers):
        for old in list(logger.handlers):
            logger.removeHandler(old)
            old.close()
        handler = RotatingFileHandler(target, maxBytes=1_000_000, backupCount=1, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s pid=%(process)d %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
```

Create `talk/config.py`:

```python
"""Settings from config.json in the Claude Talk folder. Anything missing or broken falls back to defaults."""
import json
from dataclasses import dataclass, fields, replace

from talk import paths
from talk.log import get_logger


@dataclass(frozen=True)
class Config:
    voice: str = "en-GB-SoniaNeural"
    rate: str = "+0%"
    full_read_max_words: int = 120
    gist_max_words: int = 60
    fallback_to_windows_voice: bool = True


def load_config() -> Config:
    path = paths.config_file()
    if not path.exists():
        return Config()
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        get_logger().warning("Ignoring unreadable config.json: %s", exc)
        return Config()
    if not isinstance(data, dict):
        get_logger().warning("Ignoring config.json: expected a JSON object")
        return Config()

    defaults = Config()
    values = {}
    for field in fields(Config):
        if field.name not in data:
            continue
        value, default = data[field.name], getattr(defaults, field.name)
        if type(value) is type(default):
            values[field.name] = value
        else:
            get_logger().warning(
                "Ignoring config.json %s=%r: expected %s", field.name, value, type(default).__name__
            )
    return replace(defaults, **values)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paths.py tests/test_log.py tests/test_config.py -v`
Expected: 12 passed

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml config.json talk tests
git commit -m "feat: scaffold package with paths, logging and config" --trailer "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" --trailer "Claude-Session: https://claude.ai/code/session_01PynKPRx4DNyfD6UkLUSyJL"
```

---

### Task 3: Turning a reply into speech (`speakable`)

**Files:**
- Create: `talk/speakable.py`
- Test: `tests/test_speakable.py`

**Interfaces:**
- Produces:
  - `to_speech(markdown: str, full_read_max_words: int = 120, gist_max_words: int = 60) -> str`
  - `split_sentences(text: str) -> list[str]`
  - `speech_chunks(text: str, max_chars: int = 250) -> list[str]`: first sentence alone, then sentences grouped up to `max_chars`
  - constants `REST_ON_SCREEN = "The rest is on screen."`, `NOTHING_TO_SAY = "Done. The details are on screen."`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_speakable.py`:

```python
import pytest

from talk.speakable import NOTHING_TO_SAY, REST_ON_SCREEN, speech_chunks, split_sentences, to_speech

LONG_LIST = "\n".join(
    f"- Updated module number {i} so that it uses the new helper consistently" for i in range(12)
)
BUILD_REPLY = (
    "I've fixed the login bug. The session token was expiring before the refresh ran, "
    "and the tests pass now.\n\n## Changes\n\n" + LONG_LIST + "\n\n```ts\nconst x = 1;\n```\n"
)
TEN_WORDS = "This sentence has exactly ten words in it right here."
HUGE_SENTENCE = " ".join(["word"] * 80) + "."

CASES = [
    ("plain chat",
     "Supabase is the better fit here. It gives you Postgres, auth and storage in one place.",
     "Supabase is the better fit here. It gives you Postgres, auth and storage in one place."),
    ("code only", "```python\nprint('hi')\n```", NOTHING_TO_SAY),
    ("link", "See [the docs](https://example.com/docs) for more.", "See the docs for more."),
    ("bare url", "Docs live at https://code.claude.com/docs/en/hooks today.", "Docs live at today."),
    ("short inline code", "Run `/voice tap` to switch.", "Run /voice tap to switch."),
    ("long inline code", "Then run `npm install --save-dev @types/node typescript` again.", "Then run again."),
    ("paths in inline code", "I changed `src/auth/session.ts:42` and `README.md`.",
     "I changed session.ts and README.md."),
    ("windows path in text", r"Edited C:\Users\olodh\Projects\claude-talk\config.json just now.",
     "Edited config.json just now."),
    ("unix path in text", "See /home/omar/app/src/main.py:10 for it.", "See main.py for it."),
    ("headings bold emoji", "## Summary\n\n**All tests pass** ✅\n\nNext I'll *tidy up* the docs.",
     "All tests pass. Next I'll tidy up the docs."),
    ("intro then list", "Changes:\n- Moved the refresh check\n- Added a test",
     "Changes: Moved the refresh check. Added a test."),
    ("table", "Here's the comparison:\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nB wins.",
     "Here's the comparison: B wins."),
    ("diagram fence", "```mermaid\ngraph TD\n  A-->B\n```\nDiagram above.", "Diagram above."),
    ("unterminated fence", "Here it is:\n```python\nprint(1)\n", "Here it is:"),
    ("snake_case kept", "The set_voice function handles it.", "The set_voice function handles it."),
    ("arrow", "Python 3.12 → 3.13 works.", "Python 3.12 to 3.13 works."),
    ("blockquote", "> Note: this is quoted.", "Note: this is quoted."),
    ("checkbox list", "- [x] Write tests\n- [ ] Ship it", "Write tests. Ship it."),
    ("html tag", "Use <kbd>Space</kbd> to talk.", "Use Space to talk."),
    ("non-ascii kept", "It costs £5 — that’s fine.", "It costs £5 — that’s fine."),
    ("empty list item dropped", "- `npm install --save-dev @types/node typescript`\n- Done", "Done."),
    ("windows line endings", "First line here.\r\n\r\nSecond line here.", "First line here. Second line here."),
    ("comparison symbols kept", "Use a < b && c > d carefully.", "Use a < b && c > d carefully."),
    ("long build reply gives gist only", BUILD_REPLY,
     "I've fixed the login bug. The session token was expiring before the refresh ran, "
     "and the tests pass now. " + REST_ON_SCREEN),
    ("long first paragraph trimmed at a sentence", " ".join([TEN_WORDS] * 8) + "\n\n" + LONG_LIST,
     " ".join([TEN_WORDS] * 6) + " " + REST_ON_SCREEN),
    ("huge first sentence cut", HUGE_SENTENCE + "\n\n" + LONG_LIST,
     " ".join(["word"] * 60) + "… " + REST_ON_SCREEN),
]


@pytest.mark.parametrize("given,expected", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_to_speech(given, expected):
    assert to_speech(given) == expected


def test_limits_are_configurable():
    reply = "One two three four five. Six seven eight nine ten.\n\nEleven twelve."
    assert to_speech(reply, full_read_max_words=100) == "One two three four five. Six seven eight nine ten. Eleven twelve."
    assert to_speech(reply, full_read_max_words=5, gist_max_words=5) == "One two three four five. " + REST_ON_SCREEN


def test_split_sentences_does_not_split_file_names():
    assert split_sentences("a.ts is fine. Next one!") == ["a.ts is fine.", "Next one!"]


def test_speech_chunks_start_with_the_first_sentence_alone():
    sentences = " ".join(f"Sentence number {i} is here." for i in range(20))
    chunks = speech_chunks("One. " + sentences)
    assert chunks[0] == "One."
    assert all(len(chunk) <= 250 for chunk in chunks)
    assert " ".join(chunks) == "One. " + sentences


def test_speech_chunks_of_nothing():
    assert speech_chunks("") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_speakable.py -v`
Expected: ERROR with `ModuleNotFoundError: No module named 'talk.speakable'`

- [ ] **Step 3: Write the implementation**

Create `talk/speakable.py`:

```python
"""Turn a Claude Code reply (Markdown) into the text that gets spoken."""
import re

REST_ON_SCREEN = "The rest is on screen."
NOTHING_TO_SAY = "Done. The details are on screen."
INLINE_CODE_MAX_WORDS = 3
INLINE_CODE_MAX_CHARS = 30

_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]*\1[ \t]*$|\Z)", re.MULTILINE | re.DOTALL)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
_RULE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_TABLE_ROW = re.compile(r"^\s*\|")
_QUOTE = re.compile(r"^\s{0,3}(>\s?)+")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_CHECKBOX = re.compile(r"^\[[ xX]\]\s+")

_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_HTML_TAG = re.compile(r"</?[A-Za-z][^>\n]*>")
_URL = re.compile(r"(?:https?://|www\.)\S+")
_PATH = re.compile(
    r"(?:[A-Za-z]:)?[\\/]?(?:[\w.~-]+[\\/])+([\w.-]+\.[A-Za-z][A-Za-z0-9]*)(?::\d+(?:[:-]\d+)?)?"
)
_FILE_LINE = re.compile(r"\b([\w-]+\.[A-Za-z][A-Za-z0-9]*):\d+(?:[:-]\d+)?\b")
_BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_ITALIC_STAR = re.compile(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])")
_ITALIC_UNDERSCORE = re.compile(r"(?<![\w_])_(?=\S)(.+?)(?<=\S)_(?![\w_])")
_STRIKE = re.compile(r"~~(.+?)~~")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?…])\s+")


def to_speech(markdown: str, full_read_max_words: int = 120, gist_max_words: int = 60) -> str:
    """Short replies are read in full; long ones give the opening paragraph, then REST_ON_SCREEN."""
    paragraphs = _paragraphs(markdown)
    if not paragraphs:
        return NOTHING_TO_SAY
    if sum(_word_count(p) for p in paragraphs) <= full_read_max_words:
        return " ".join(paragraphs)
    return f"{_trim(paragraphs[0], gist_max_words)} {REST_ON_SCREEN}"


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_BREAK.split(text.strip()) if s]


def speech_chunks(text: str, max_chars: int = 250) -> list[str]:
    """First sentence on its own (so speech starts fast), then sentences grouped up to max_chars."""
    sentences = split_sentences(text)
    if not sentences:
        return []
    chunks = [sentences[0]]
    current = ""
    for sentence in sentences[1:]:
        if current and len(current) + 1 + len(sentence) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def _paragraphs(markdown: str) -> list[str]:
    text = _FENCE.sub("\n", markdown.replace("\r\n", "\n"))
    text = _HTML_COMMENT.sub("", text)
    paragraphs: list[str] = []
    current: list[str] = []
    current_is_list = False

    for raw in text.split("\n"):
        if not raw.strip() or _HEADING.match(raw) or _RULE.match(raw) or _TABLE_ROW.match(raw):
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        line = _QUOTE.sub("", raw)
        is_list = bool(_LIST_ITEM.match(line))
        if is_list:
            line = _CHECKBOX.sub("", _LIST_ITEM.sub("", line, count=1))
        if current and is_list != current_is_list:
            paragraphs.append(" ".join(current))
            current = []
        line = _clean_inline(line)
        if not line:
            continue
        if not current:
            current_is_list = is_list
        current.append(_end_sentence(line) if is_list else line)

    if current:
        paragraphs.append(" ".join(current))
    return [_end_sentence(p) for p in paragraphs]


def _clean_inline(line: str) -> str:
    line = _IMAGE.sub("", line)
    line = _LINK.sub(r"\1", line)
    line = _INLINE_CODE.sub(_speak_inline_code, line)
    line = _HTML_TAG.sub("", line)
    line = _URL.sub("", line)
    line = _PATH.sub(lambda m: m.group(1), line)
    line = _FILE_LINE.sub(r"\1", line)
    line = _BOLD.sub(r"\2", line)
    line = _ITALIC_STAR.sub(r"\1", line)
    line = _ITALIC_UNDERSCORE.sub(r"\1", line)
    line = _STRIKE.sub(r"\1", line)
    line = line.replace("→", " to ")
    line = _EMOJI.sub("", line)
    line = re.sub(r"\(\s*\)", "", line)
    line = re.sub(r"\s+", " ", line)
    line = re.sub(r"\s+([,.;:!?])", r"\1", line)
    return line.strip()


def _speak_inline_code(match: re.Match) -> str:
    code = match.group(1).strip()
    path = _PATH.fullmatch(code)
    if path:
        return path.group(1)
    code = _FILE_LINE.sub(r"\1", code)
    if len(code) <= INLINE_CODE_MAX_CHARS and len(code.split()) <= INLINE_CODE_MAX_WORDS:
        return code
    return ""


def _end_sentence(text: str) -> str:
    if text.rstrip("\"')]*")[-1:] in (".", "!", "?", ":", ";", "…"):
        return text
    return text + "."


def _word_count(text: str) -> int:
    return len(text.split())


def _trim(paragraph: str, max_words: int) -> str:
    kept: list[str] = []
    count = 0
    for sentence in split_sentences(paragraph):
        words = _word_count(sentence)
        if not kept and words > max_words:
            return " ".join(sentence.split()[:max_words]) + "…"
        if count + words > max_words:
            break
        kept.append(sentence)
        count += words
    return " ".join(kept)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_speakable.py -v`
Expected: 30 passed

- [ ] **Step 5: Commit**

```powershell
git add talk/speakable.py tests/test_speakable.py
git commit -m "feat: turn Markdown replies into speakable text" --trailer "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" --trailer "Claude-Session: https://claude.ai/code/session_01PynKPRx4DNyfD6UkLUSyJL"
```

---

### Task 4: The per-session switch

**Files:**
- Create: `talk/switch.py`
- Test: `tests/test_switch.py`

**Interfaces:**
- Consumes: `talk.paths.sessions_dir()`, `talk.paths.state_dir()`
- Produces:
  - `is_on(session_id: str) -> bool` (False for empty/invalid ids, never raises)
  - `turn_on(session_id: str) -> None` (raises `ValueError` for an empty id; also refreshes the marker's age)
  - `turn_off(session_id: str) -> None` (never raises)
  - `toggle(session_id: str, prompt_id: str | None = None) -> bool`: the new state. Repeating the last `(session_id, prompt_id)` changes nothing.
  - `cleanup_stale(max_age_days: int = 7, now: float | None = None) -> int`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_switch.py`:

```python
import os
import time

import pytest

from talk import paths, switch


def test_off_by_default():
    assert switch.is_on("s1") is False


def test_toggle_on_then_off():
    assert switch.toggle("s1") is True
    assert switch.is_on("s1") is True
    assert switch.toggle("s1") is False
    assert switch.is_on("s1") is False


def test_sessions_are_independent():
    switch.turn_on("s1")
    assert switch.is_on("s1") is True
    assert switch.is_on("s2") is False


def test_same_prompt_twice_toggles_once():
    assert switch.toggle("s1", "p1") is True
    assert switch.toggle("s1", "p1") is True
    assert switch.is_on("s1") is True
    assert switch.toggle("s1", "p2") is False


def test_empty_or_odd_session_ids():
    assert switch.is_on("") is False
    assert switch.is_on("!!!") is False
    switch.turn_off("")
    with pytest.raises(ValueError):
        switch.toggle("")


def test_session_ids_cannot_escape_the_folder():
    switch.turn_on("../../evil")
    assert (paths.sessions_dir() / "evil").exists()


def test_cleanup_removes_only_old_markers():
    switch.turn_on("old")
    switch.turn_on("fresh")
    eight_days_ago = time.time() - 8 * 86400
    os.utime(paths.sessions_dir() / "old", (eight_days_ago, eight_days_ago))
    assert switch.cleanup_stale() == 1
    assert switch.is_on("old") is False
    assert switch.is_on("fresh") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_switch.py -v`
Expected: ERROR with `ImportError: cannot import name 'switch' from 'talk'`

- [ ] **Step 3: Write the implementation**

Create `talk/switch.py`:

```python
"""Per-session talk mode, stored as one marker file per session in state/sessions/."""
import time
from pathlib import Path

from talk import paths

STALE_AFTER_DAYS = 7


def _marker(session_id: str) -> Path:
    safe = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")
    if not safe:
        raise ValueError("session_id is empty")
    return paths.sessions_dir() / safe


def is_on(session_id: str) -> bool:
    try:
        return _marker(session_id).exists()
    except ValueError:
        return False


def turn_on(session_id: str) -> None:
    _marker(session_id).touch()


def turn_off(session_id: str) -> None:
    try:
        _marker(session_id).unlink(missing_ok=True)
    except ValueError:
        pass


def toggle(session_id: str, prompt_id: str | None = None) -> bool:
    """Flip talk mode and return the new state.

    The same /talk can reach us through two hooks (UserPromptSubmit and UserPromptExpansion)
    with the same prompt_id; the repeat changes nothing."""
    _marker(session_id)  # validates the id before anything changes
    last = paths.state_dir() / "last_toggle"
    key = f"{session_id}:{prompt_id}" if prompt_id else None
    if key and last.exists() and last.read_text(encoding="utf-8") == key:
        return is_on(session_id)
    if is_on(session_id):
        turn_off(session_id)
        new_state = False
    else:
        turn_on(session_id)
        new_state = True
    if key:
        last.write_text(key, encoding="utf-8")
    return new_state


def cleanup_stale(max_age_days: int = STALE_AFTER_DAYS, now: float | None = None) -> int:
    cutoff = (time.time() if now is None else now) - max_age_days * 86400
    removed = 0
    for marker in paths.sessions_dir().iterdir():
        try:
            if marker.stat().st_mtime < cutoff:
                marker.unlink()
                removed += 1
        except OSError:
            continue
    return removed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_switch.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```powershell
git add talk/switch.py tests/test_switch.py
git commit -m "feat: add per-session talk switch" --trailer "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" --trailer "Claude-Session: https://claude.ai/code/session_01PynKPRx4DNyfD6UkLUSyJL"
```

---

### Task 5: Process helpers and the one-speaker registry

**Files:**
- Create: `talk/procs.py`, `talk/control.py`
- Test: `tests/test_control.py`, `tests/fake_speaker.py`

**Interfaces:**
- Consumes: `talk.paths.state_dir()`, `talk.paths.jobs_dir()`
- Produces:
  - `talk.procs.spawn_detached(args: list[str]) -> int` (pid), `is_alive(pid: int) -> bool`, `kill_tree(pid: int) -> None`, constant `CREATE_NO_WINDOW`
  - `talk.control.start_speaking(text: str, session_id: str, command_for: Callable[[Path], list[str]] = speaker_command) -> int`. It writes `state/jobs/<token>.json` = `{"token", "session_id", "text"}`, spawns the speaker and records `state/speaker.json` = `{"pid", "token", "session_id", "started"}`.
  - `talk.control.stop_speaking(session_id: str | None = None, wait: float = 0.5) -> bool`
  - `talk.control.should_stop(token: str) -> bool`: True if a stop was requested for this token, or `speaker.json` names a different token (superseded)
  - `talk.control.clear_speaker(token: str) -> None`
  - `talk.control.current_speaker() -> dict | None`
  - `talk.control.speaker_command(job_path: Path) -> list[str]`: `[<venv pythonw.exe>, "-m", "talk.speaker", <job_path>]`

- [ ] **Step 1: Write the fake speaker and failing tests**

Create `tests/fake_speaker.py`:

```python
"""Stand-in for talk.speaker in control tests.

Usage: python fake_speaker.py <job.json> <polite|stubborn>
polite: waits until control.should_stop(token), then clears itself and exits.
stubborn: ignores stop requests and sleeps for 30 s."""
import json
import sys
import time
from pathlib import Path

from talk import control

job_path = Path(sys.argv[1])
job = json.loads(job_path.read_text(encoding="utf-8"))
job_path.with_suffix(".ready").write_text("ready", encoding="utf-8")
if sys.argv[2] == "stubborn":
    time.sleep(30)
else:
    deadline = time.monotonic() + 30
    while not control.should_stop(job["token"]) and time.monotonic() < deadline:
        time.sleep(0.02)
    control.clear_speaker(job["token"])
```

Create `tests/test_control.py`:

```python
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
    assert command[1:3] == ["-m", "talk.speaker"]
    assert command[3] == str(tmp_path / "job.json")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_control.py -v`
Expected: ERROR with `ImportError: cannot import name 'control' from 'talk'`

- [ ] **Step 3: Write the implementation**

Create `talk/procs.py`:

```python
"""Windows process helpers: start a process that outlives us, check it, kill it with its children."""
import ctypes
import subprocess
from ctypes import wintypes

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NO_WINDOW = 0x08000000
_SYNCHRONIZE = 0x00100000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_WAIT_TIMEOUT = 0x102

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)


def spawn_detached(args: list[str]) -> int:
    """Start args with no console and outside our job (if allowed), so it survives the hook exiting."""
    base = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    options = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    try:
        return subprocess.Popen(args, creationflags=base | CREATE_BREAKAWAY_FROM_JOB, **options).pid
    except OSError:
        return subprocess.Popen(args, creationflags=base, **options).pid


def is_alive(pid: int) -> bool:
    handle = _kernel32.OpenProcess(_SYNCHRONIZE | _PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        return _kernel32.WaitForSingleObject(handle, 0) == _WAIT_TIMEOUT
    finally:
        _kernel32.CloseHandle(handle)


def kill_tree(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, check=False,
    )
```

Create `talk/control.py`:

```python
"""Start and stop the one speaker process that may be talking at any time.

state/speaker.json records the current speaker (pid, token, session_id).
state/stop holds the token of a speaker that has been asked to stop."""
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Callable

from talk import paths, procs

STOP_WAIT_SECONDS = 0.5


def _speaker_file() -> Path:
    return paths.state_dir() / "speaker.json"


def _stop_file() -> Path:
    return paths.state_dir() / "stop"


def _stop_target() -> str | None:
    try:
        return _stop_file().read_text(encoding="utf-8").strip()
    except OSError:
        return None


def current_speaker() -> dict | None:
    try:
        data = json.loads(_speaker_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and isinstance(data.get("pid"), int) and isinstance(data.get("token"), str):
        return data
    return None


def should_stop(token: str) -> bool:
    """True when this speaker was asked to stop, or a newer speaker has taken over."""
    if _stop_target() == token:
        return True
    current = current_speaker()
    return current is not None and current["token"] != token


def clear_speaker(token: str) -> None:
    """Forget this speaker (if it is still the registered one) and its stop request."""
    current = current_speaker()
    if current and current["token"] == token:
        _speaker_file().unlink(missing_ok=True)
    if _stop_target() == token:
        _stop_file().unlink(missing_ok=True)


def stop_speaking(session_id: str | None = None, wait: float = STOP_WAIT_SECONDS) -> bool:
    """Stop the current speaker (only if it belongs to session_id, when given). True if one was stopped."""
    current = current_speaker()
    if current is None:
        return False
    if session_id is not None and current.get("session_id") != session_id:
        return False
    pid, token = current["pid"], current["token"]
    if procs.is_alive(pid):
        _stop_file().write_text(token, encoding="utf-8")
        deadline = time.monotonic() + wait
        while procs.is_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        if procs.is_alive(pid):
            procs.kill_tree(pid)
    clear_speaker(token)
    return True


def speaker_command(job_path: Path) -> list[str]:
    """pythonw.exe (no console window) from this same environment, running talk.speaker."""
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    return [str(pythonw if pythonw.exists() else python), "-m", "talk.speaker", str(job_path)]


def start_speaking(
    text: str, session_id: str, command_for: Callable[[Path], list[str]] = speaker_command
) -> int:
    """Silence any current speaker, then start a new one for text. Returns its pid."""
    stop_speaking()
    token = uuid.uuid4().hex
    job_path = paths.jobs_dir() / f"{token}.json"
    job_path.write_text(json.dumps({"token": token, "session_id": session_id, "text": text}), encoding="utf-8")
    pid = procs.spawn_detached(command_for(job_path))
    _speaker_file().write_text(
        json.dumps({"pid": pid, "token": token, "session_id": session_id, "started": time.time()}),
        encoding="utf-8",
    )
    return pid
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_control.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```powershell
git add talk/procs.py talk/control.py tests/test_control.py tests/fake_speaker.py
git commit -m "feat: add one-speaker-at-a-time process control" --trailer "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" --trailer "Claude-Session: https://claude.ai/code/session_01PynKPRx4DNyfD6UkLUSyJL"
```

---

### Task 6: Key watching and the speaking loop

The orchestration logic, tested entirely with fakes. The real audio and voice adapters come in Task 7.

**Files:**
- Create: `talk/keys.py`, `talk/speaker.py` (the `speak()` loop and `Deps` only; `main()` is added in Task 7)
- Test: `tests/test_keys.py`, `tests/test_speaker.py`

**Interfaces:**
- Consumes: `talk.speakable.speech_chunks(text) -> list[str]`
- Produces:
  - `talk.keys.KeyWatcher(keys=(VK_SPACE, VK_ESCAPE), read=<GetAsyncKeyState>)` with `.prime() -> None` and `.pressed() -> bool`
  - `talk.speaker.Deps(synthesize: Callable[[str, Path], None], open_player: Callable[[Path], Player], start_fallback: Callable[[str], Process] | None, should_stop: Callable[[], bool], work_dir: Path)`
  - `talk.speaker.speak(text: str, deps: Deps, first_timeout: float = 5.0, next_timeout: float = 15.0) -> str`, returning `"finished" | "stopped" | "fallback" | "failed"`
  - `Player` protocol: `play()`, `is_playing() -> bool`, `close()`. `Process` protocol: `poll() -> int | None`, `kill()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_keys.py`:

```python
from talk.keys import VK_ESCAPE, VK_SPACE, KeyWatcher

DOWN = 0x8000
TAPPED = 0x0001


class ScriptedKeys:
    """Returns the next scripted GetAsyncKeyState value for each key (0 once the script runs out)."""

    def __init__(self, **scripts):
        self.scripts = {VK_SPACE: list(scripts.get("space", [])), VK_ESCAPE: list(scripts.get("esc", []))}

    def __call__(self, vk: int) -> int:
        script = self.scripts[vk]
        return script.pop(0) if script else 0


def watcher(**scripts) -> KeyWatcher:
    w = KeyWatcher(read=ScriptedKeys(**scripts))
    w.prime()
    return w


def test_nothing_pressed():
    w = watcher()
    assert w.pressed() is False


def test_space_pressed_after_start():
    w = watcher(space=[0, 0, DOWN])
    assert w.pressed() is False
    assert w.pressed() is True


def test_escape_pressed_after_start():
    w = watcher(esc=[0, DOWN])
    assert w.pressed() is True


def test_key_held_at_start_only_counts_after_release():
    w = watcher(space=[DOWN, DOWN | TAPPED, DOWN, 0, DOWN])
    assert w.pressed() is False  # still held (auto-repeat)
    assert w.pressed() is False  # still held
    assert w.pressed() is False  # released
    assert w.pressed() is True   # pressed again


def test_quick_tap_between_polls_counts():
    w = watcher(space=[0, TAPPED])
    assert w.pressed() is True
```

Create `tests/test_speaker.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_keys.py tests/test_speaker.py -v`
Expected: ERROR with `ModuleNotFoundError: No module named 'talk.keys'` / `'talk.speaker'`

- [ ] **Step 3: Write the implementation**

Create `talk/keys.py`:

```python
"""Notice a fresh press of Space or Esc while Claude is talking."""
import ctypes
from typing import Callable, Iterable

VK_SPACE = 0x20
VK_ESCAPE = 0x1B
_DOWN = 0x8000
_PRESSED_SINCE_LAST_CALL = 0x0001

_user32 = ctypes.WinDLL("user32")
_user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
_user32.GetAsyncKeyState.restype = ctypes.c_short


def _read_key_state(vk: int) -> int:
    return _user32.GetAsyncKeyState(vk) & 0xFFFF


class KeyWatcher:
    """pressed() is True for a press that starts after prime().

    A key already held when speech starts only counts once it has been released and pressed again."""

    def __init__(self, keys: Iterable[int] = (VK_SPACE, VK_ESCAPE), read: Callable[[int], int] = _read_key_state):
        self._keys = tuple(keys)
        self._read = read
        self._down: dict[int, bool] = {}

    def prime(self) -> None:
        for vk in self._keys:
            self._down[vk] = bool(self._read(vk) & _DOWN)  # reading also clears the "pressed since" bit

    def pressed(self) -> bool:
        fresh = False
        for vk in self._keys:
            state = self._read(vk)
            down = bool(state & _DOWN)
            if not self._down.get(vk, False) and (down or state & _PRESSED_SINCE_LAST_CALL):
                fresh = True
            self._down[vk] = down
        return fresh
```

Create `talk/speaker.py`:

```python
"""The speaker process: speaks one reply, sentence by sentence, and stops the moment it should."""
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from talk.log import get_logger
from talk.speakable import speech_chunks

FIRST_AUDIO_TIMEOUT = 5.0
NEXT_AUDIO_TIMEOUT = 15.0
POLL_SECONDS = 0.05
_STOPPED = object()


class Player(Protocol):
    def play(self) -> None: ...
    def is_playing(self) -> bool: ...
    def close(self) -> None: ...


class Process(Protocol):
    def poll(self) -> int | None: ...
    def kill(self) -> None: ...


@dataclass
class Deps:
    synthesize: Callable[[str, Path], None]
    open_player: Callable[[Path], Player]
    start_fallback: Callable[[str], Process] | None
    should_stop: Callable[[], bool]
    work_dir: Path


def speak(
    text: str, deps: Deps, first_timeout: float = FIRST_AUDIO_TIMEOUT, next_timeout: float = NEXT_AUDIO_TIMEOUT
) -> str:
    """Speak text. Returns "finished", "stopped", "fallback" (finished in the Windows voice) or "failed"."""
    chunks = speech_chunks(text)
    results: queue.Queue = queue.Queue()
    cancel = threading.Event()

    def produce() -> None:
        for index, chunk in enumerate(chunks):
            if cancel.is_set():
                return
            path = deps.work_dir / f"chunk{index}.mp3"
            try:
                deps.synthesize(chunk, path)
            except Exception as exc:
                results.put(exc)
                return
            results.put(path)

    threading.Thread(target=produce, daemon=True).start()
    try:
        for index in range(len(chunks)):
            item = _wait_for(results, first_timeout if index == 0 else next_timeout, deps.should_stop)
            if item is _STOPPED:
                return "stopped"
            if item is None or isinstance(item, Exception):
                get_logger().warning("online voice failed (%s); using fallback", item or "timed out")
                return _fallback(" ".join(chunks[index:]), deps)
            try:
                if _play(item, deps) == "stopped":
                    return "stopped"
            except Exception:
                get_logger().exception("playback failed; using fallback")
                return _fallback(" ".join(chunks[index:]), deps)
        return "finished"
    finally:
        cancel.set()


def _wait_for(results: queue.Queue, timeout: float, should_stop: Callable[[], bool]):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if should_stop():
            return _STOPPED
        try:
            return results.get(timeout=POLL_SECONDS)
        except queue.Empty:
            continue
    return None


def _play(path: Path, deps: Deps) -> str:
    player = deps.open_player(path)
    try:
        player.play()
        while player.is_playing():
            if deps.should_stop():
                return "stopped"
            time.sleep(POLL_SECONDS)
        return "done"
    finally:
        player.close()


def _fallback(text: str, deps: Deps) -> str:
    if deps.start_fallback is None:
        return "failed"
    proc = deps.start_fallback(text)
    while proc.poll() is None:
        if deps.should_stop():
            proc.kill()
            return "stopped"
        time.sleep(POLL_SECONDS)
    return "fallback"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_keys.py tests/test_speaker.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```powershell
git add talk/keys.py talk/speaker.py tests/test_keys.py tests/test_speaker.py
git commit -m "feat: add key watcher and speaking loop" --trailer "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" --trailer "Claude-Session: https://claude.ai/code/session_01PynKPRx4DNyfD6UkLUSyJL"
```

---

### Task 7: Real audio, voices and the speaker process

**Files:**
- Create: `talk/playback.py`, `talk/tts.py`, `scripts/say.py`
- Modify: `talk/speaker.py` (add `main()`, `_speak_job()`, `_sweep_old_files()`)
- Test: `tests/test_playback.py`, `tests/test_tts.py`, add to `tests/test_speaker.py`

**Interfaces:**
- Consumes: `talk.control.should_stop(token)`, `talk.control.clear_speaker(token)`, `talk.config.load_config()`, `talk.keys.KeyWatcher`, `talk.speaker.speak/Deps`
- Produces:
  - `talk.playback.Mp3Player(path: Path)` with `.play()`, `.is_playing() -> bool`, `.close()`; `talk.playback.PlaybackError`
  - `talk.tts.synthesize(text: str, voice: str, rate: str, out_path: Path) -> None`, `talk.tts.start_windows_voice(text: str, work_dir: Path) -> subprocess.Popen`, `talk.tts.windows_voice_command(text_file: Path) -> list[str]`, `talk.tts.TtsError`
  - `talk.speaker.main(argv: list[str] | None = None) -> int`, run as `python -m talk.speaker <job.json>`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_playback.py`:

```python
import time
import wave
from pathlib import Path

import pytest

from talk.playback import Mp3Player, PlaybackError


def silent_wav(path: Path, seconds: float = 0.3) -> Path:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b"\x00\x00" * int(16000 * seconds))
    return path


def test_plays_a_file_to_the_end(tmp_path):
    player = Mp3Player(silent_wav(tmp_path / "silence.wav"))
    player.play()
    deadline = time.monotonic() + 3
    while player.is_playing():
        assert time.monotonic() < deadline, "playback never finished"
        time.sleep(0.05)
    player.close()


def test_close_is_safe_to_repeat(tmp_path):
    player = Mp3Player(silent_wav(tmp_path / "silence.wav"))
    player.play()
    player.close()
    player.close()


def test_missing_file_raises(tmp_path):
    with pytest.raises(PlaybackError):
        Mp3Player(tmp_path / "missing.mp3")
```

Create `tests/test_tts.py`:

```python
import os
from pathlib import Path

import pytest

from talk import tts


def test_windows_voice_command_reads_the_text_file_as_utf8():
    command = tts.windows_voice_command(Path(r"C:\work\fallback.txt"))
    assert command[:4] == ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
    assert "System.Speech" in command[4]
    assert r"ReadAllText('C:\work\fallback.txt', [Text.Encoding]::UTF8)" in command[4]


def test_windows_voice_command_escapes_quotes():
    command = tts.windows_voice_command(Path(r"C:\it's\fallback.txt"))
    assert r"'C:\it''s\fallback.txt'" in command[4]


@pytest.mark.skipif(os.environ.get("TALK_NETWORK_TESTS") != "1", reason="set TALK_NETWORK_TESTS=1 to call Microsoft's voice service")
def test_synthesize_writes_mp3(tmp_path):
    out = tmp_path / "hello.mp3"
    tts.synthesize("Talk mode is working.", "en-GB-SoniaNeural", "+0%", out)
    assert out.stat().st_size > 1000
```

In `tests/test_speaker.py`, replace the import lines at the top with:

```python
import json
import os
import time

from talk import control, paths, speaker
from talk.speaker import Deps, speak
```

Then append these tests to the end of the file:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_playback.py tests/test_tts.py tests/test_speaker.py -v`
Expected: ERROR with `ModuleNotFoundError: No module named 'talk.playback'` (and `talk.tts`); `AttributeError: module 'talk.speaker' has no attribute 'main'`

- [ ] **Step 3: Write the implementation**

Create `talk/playback.py`:

```python
"""Play an audio file through Windows' built-in media control interface (MCI). No extra libraries."""
import ctypes
import itertools
import os
from ctypes import wintypes
from pathlib import Path

_winmm = ctypes.WinDLL("winmm")
_winmm.mciSendStringW.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.UINT, wintypes.HANDLE)
_winmm.mciSendStringW.restype = wintypes.DWORD
_winmm.mciGetErrorStringW.argtypes = (wintypes.DWORD, wintypes.LPWSTR, wintypes.UINT)
_aliases = itertools.count()


class PlaybackError(Exception):
    pass


def _mci(command: str) -> str:
    reply = ctypes.create_unicode_buffer(256)
    error = _winmm.mciSendStringW(command, reply, 255, None)
    if error:
        message = ctypes.create_unicode_buffer(256)
        _winmm.mciGetErrorStringW(error, message, 255)
        raise PlaybackError(f"{command!r} failed: {message.value}")
    return reply.value


class Mp3Player:
    """Plays one MP3 (or WAV) file. Use from the thread that created it."""

    def __init__(self, path: Path):
        self._alias = f"talk{os.getpid()}x{next(_aliases)}"
        _mci(f'open "{path}" type mpegvideo alias {self._alias}')

    def play(self) -> None:
        _mci(f"play {self._alias}")

    def is_playing(self) -> bool:
        return _mci(f"status {self._alias} mode") != "stopped"

    def close(self) -> None:
        for command in (f"stop {self._alias}", f"close {self._alias}"):
            try:
                _mci(command)
            except PlaybackError:
                pass
```

Create `talk/tts.py`:

```python
"""Speech synthesis: Microsoft's online neural voices, with the Windows built-in voice as a fallback."""
import asyncio
import subprocess
from pathlib import Path

from talk.procs import CREATE_NO_WINDOW


class TtsError(Exception):
    pass


def synthesize(text: str, voice: str, rate: str, out_path: Path) -> None:
    """Write MP3 audio of text to out_path using edge-tts. Raises on any failure."""
    import edge_tts

    async def run() -> None:
        communicate = edge_tts.Communicate(text, voice, rate=rate, connect_timeout=5, receive_timeout=20)
        await communicate.save(str(out_path))

    asyncio.run(run())
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise TtsError("edge-tts returned no audio")


def windows_voice_command(text_file: Path) -> list[str]:
    path = str(text_file).replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Speak([IO.File]::ReadAllText('{path}', [Text.Encoding]::UTF8))"
    )
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]


def start_windows_voice(text: str, work_dir: Path) -> subprocess.Popen:
    """Start speaking text in the Windows built-in voice. Kill the returned process to stop it."""
    text_file = work_dir / "fallback.txt"
    text_file.write_text(text, encoding="utf-8")
    return subprocess.Popen(
        windows_voice_command(text_file),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )
```

In `talk/speaker.py`, replace the import block at the top with:

```python
"""The speaker process: python -m talk.speaker <job.json>

Started detached by control.start_speaking. Speaks one reply, sentence by sentence, and stops
the moment Space/Esc is pressed, a stop is requested, or a newer reply takes over."""
import json
import queue
import shutil
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from talk import control, paths
from talk.config import load_config
from talk.log import get_logger
from talk.speakable import speech_chunks
```

Add below the existing constants:

```python
SWEEP_AFTER_SECONDS = 3600
```

Append to the end of `talk/speaker.py`:

```python
def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    log = get_logger()
    token = ""
    try:
        job_path = Path(argv[0])
        job = json.loads(job_path.read_text(encoding="utf-8"))
        job_path.unlink(missing_ok=True)
        token = job["token"]
        _sweep_old_files()
        outcome = _speak_job(job["text"], token)
        log.info("speaker %s: %s", token[:8], outcome)
    except Exception:
        log.exception("speaker failed")
    finally:
        if token:
            control.clear_speaker(token)
    return 0


def _speak_job(text: str, token: str) -> str:
    from talk import playback, tts
    from talk.keys import KeyWatcher

    cfg = load_config()
    keys = KeyWatcher()
    keys.prime()

    def should_stop() -> bool:
        key_pressed = keys.pressed()  # poll every time so held/released keys are tracked
        return key_pressed or control.should_stop(token)

    with tempfile.TemporaryDirectory(prefix="speak-", dir=paths.state_dir(), ignore_cleanup_errors=True) as tmp:
        work_dir = Path(tmp)
        deps = Deps(
            synthesize=lambda chunk, out: tts.synthesize(chunk, cfg.voice, cfg.rate, out),
            open_player=playback.Mp3Player,
            start_fallback=(lambda rest: tts.start_windows_voice(rest, work_dir))
            if cfg.fallback_to_windows_voice else None,
            should_stop=should_stop,
            work_dir=work_dir,
        )
        return speak(text, deps)


def _sweep_old_files() -> None:
    """Remove temp folders and job files left behind by speakers that were killed."""
    cutoff = time.time() - SWEEP_AFTER_SECONDS
    leftovers = list(paths.state_dir().glob("speak-*")) + list(paths.jobs_dir().glob("*.json"))
    for path in leftovers:
        try:
            if path.stat().st_mtime >= cutoff:
                continue
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink()
        except OSError:
            continue


if __name__ == "__main__":
    sys.exit(main())
```

Create `scripts/say.py`:

```python
"""Manual smoke test: speak text through the real pipeline (detached speaker, online voice, playback).

Usage: .venv\\Scripts\\python.exe scripts\\say.py "Hello there. This is Claude Talk."
Press Space or Esc while it talks to check that it stops."""
import sys

from talk import control
from talk.speakable import to_speech

text = " ".join(sys.argv[1:]) or "Hello. This is Claude Talk, reading a reply aloud. Press Space to stop me."
speech = to_speech(text)
print(f"Speaking: {speech}")
print(f"Speaker pid: {control.start_speaking(speech, 'manual-test')}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest -v`
Expected: all tests pass, with `test_synthesize_writes_mp3` skipped

Then run the network test once:

```powershell
$env:TALK_NETWORK_TESTS = "1"; .venv\Scripts\python.exe -m pytest tests/test_tts.py -v; Remove-Item Env:TALK_NETWORK_TESTS
```

Expected: 3 passed

- [ ] **Step 5: Smoke test with real audio (needs speakers or headphones)**

Run: `.venv\Scripts\python.exe scripts\say.py "Hello there. This is Claude Talk. If you can hear this sentence, the online voice works."`
Expected: a British voice speaks all three sentences within about 2 seconds. `logs\talk.log` ends with `speaker xxxxxxxx: finished`.

Run it again and press Space after the first sentence.
Expected: speech stops at once, and the log shows `: stopped`.

Disconnect from the network (Wi-Fi off) and run it once more.
Expected: a pause of up to 5 seconds, then the Windows voice reads it. The log shows `using fallback` and `: fallback`. Turn the network back on.

- [ ] **Step 6: Commit**

```powershell
git add talk/playback.py talk/tts.py talk/speaker.py scripts/say.py tests/test_playback.py tests/test_tts.py tests/test_speaker.py
git commit -m "feat: add audio playback, voices and the speaker process" --trailer "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" --trailer "Claude-Session: https://claude.ai/code/session_01PynKPRx4DNyfD6UkLUSyJL"
```

---

### Task 8: Hook entry points

**Files:**
- Create: `talk/hooks.py`
- Test: `tests/test_hooks.py`

**Interfaces:**
- Consumes: `switch.is_on/turn_on/turn_off/toggle/cleanup_stale`, `control.start_speaking/stop_speaking`, `procs.is_alive`, `load_config()`, `to_speech()`, and the Task 1 findings (`PROMPT_FIELDS`, `WAIT_FOR_SPEAKER`)
- Produces: `python -m talk.hooks <prompt|toggle|stop|session-end>`; `talk.hooks.main(argv=None, stdin=None, stdout=None) -> int` (stdin/stdout are binary streams); constants `TALK_ON`, `TALK_OFF`, `SETUP_BROKEN`, `NUDGE`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_hooks.py`:

```python
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


def test_toggle_refuses_when_voice_package_is_missing(monkeypatch):
    monkeypatch.setattr(hooks, "tts_available", lambda: False)
    assert run("toggle", {"session_id": "s1"}) == block(hooks.SETUP_BROKEN)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_hooks.py -v`
Expected: ERROR with `ImportError: cannot import name 'hooks' from 'talk'`

- [ ] **Step 3: Write the implementation**

Create `talk/hooks.py`. If the Task 1 findings note names a different prompt field, add it to `PROMPT_FIELDS`.

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_hooks.py -v`
Expected: 16 passed

- [ ] **Step 5: Try a hook by hand, exactly as Claude Code will call it**

```powershell
'{"session_id": "manual", "prompt_id": "x1"}' | .venv\Scripts\python.exe -m talk.hooks toggle
'{"session_id": "manual", "prompt_id": "x2"}' | .venv\Scripts\python.exe -m talk.hooks toggle
```

Expected: the first prints `{"decision": "block", "reason": "\ud83d\udd0a Talk mode on: ..."}`, the second prints `... Talk mode off."}`, with nothing else on screen. Clean up with `Remove-Item state\sessions\manual -ErrorAction SilentlyContinue`.

- [ ] **Step 6: Commit**

```powershell
git add talk/hooks.py tests/test_hooks.py
git commit -m "feat: add Claude Code hook entry points" --trailer "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" --trailer "Claude-Session: https://claude.ai/code/session_01PynKPRx4DNyfD6UkLUSyJL"
```

---

### Task 9: Installer, `/talk` command and README

**Files:**
- Create: `talk/install.py`, `README.md`
- Test: `tests/test_install.py`
- Modifies on the real machine (Step 5): `C:\Users\olodh\.claude\settings.json` (backed up first), `C:\Users\olodh\.claude\commands\talk.md`

**Interfaces:**
- Consumes: `python -m talk.hooks <event>` from Task 8
- Produces: `python -m talk.install [--uninstall] [--claude-dir DIR]`; `merge_settings(settings: dict, python: str) -> dict`; `remove_from_settings(settings: dict) -> dict`; `COMMAND_MD: str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_install.py`:

```python
import copy
import json

from talk import install

PY = r"C:\venv\Scripts\python.exe"
EXISTING = {
    "model": "opus",
    "voiceEnabled": True,
    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "notify.exe"}]}]},
}


def ours(event_arg, **extra):
    return {"type": "command", "command": PY, "args": ["-m", "talk.hooks", event_arg], **extra}


def test_merge_adds_every_hook_and_tap_mode():
    before = copy.deepcopy(EXISTING)
    merged = install.merge_settings(EXISTING, PY)
    hooks = merged["hooks"]
    assert hooks["UserPromptSubmit"] == [{"hooks": [ours("prompt", timeout=10)]}]
    assert hooks["UserPromptExpansion"] == [{"matcher": "talk", "hooks": [ours("toggle", timeout=10)]}]
    assert hooks["Stop"] == [EXISTING["hooks"]["Stop"][0], {"hooks": [ours("stop", **{"async": True})]}]
    assert hooks["SessionEnd"] == [{"hooks": [ours("session-end", timeout=10)]}]
    assert merged["voice"] == {"enabled": True, "mode": "tap"}
    assert merged["model"] == "opus"
    assert merged["voiceEnabled"] is True
    assert EXISTING == before  # input untouched


def test_merging_twice_is_the_same_as_once():
    once = install.merge_settings(EXISTING, PY)
    assert install.merge_settings(once, PY) == once


def test_merge_keeps_other_voice_settings():
    merged = install.merge_settings({"voice": {"enabled": False, "autoSubmit": True}}, PY)
    assert merged["voice"] == {"enabled": True, "mode": "tap", "autoSubmit": True}


def test_remove_takes_out_only_our_hooks():
    removed = install.remove_from_settings(install.merge_settings(EXISTING, PY))
    assert removed["hooks"] == EXISTING["hooks"]


def test_remove_drops_an_empty_hooks_section():
    removed = install.remove_from_settings(install.merge_settings({}, PY))
    assert "hooks" not in removed


def test_install_and_uninstall_on_disk(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps(EXISTING), encoding="utf-8")
    assert install.main(["--claude-dir", str(tmp_path)]) == 0
    settings = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert "UserPromptExpansion" in settings["hooks"]
    assert (tmp_path / "commands" / "talk.md").read_text(encoding="utf-8") == install.COMMAND_MD
    assert json.loads((tmp_path / "settings.json.bak-claude-talk").read_text(encoding="utf-8")) == EXISTING

    assert install.main(["--claude-dir", str(tmp_path), "--uninstall"]) == 0
    settings = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert settings["hooks"] == EXISTING["hooks"]
    assert not (tmp_path / "commands" / "talk.md").exists()


def test_install_without_existing_settings(tmp_path):
    assert install.main(["--claude-dir", str(tmp_path)]) == 0
    assert "hooks" in json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_install.py -v`
Expected: ERROR with `ImportError: cannot import name 'install' from 'talk'`

- [ ] **Step 3: Write the implementation**

Create `talk/install.py`:

```python
"""Register Claude Talk with Claude Code: python -m talk.install [--uninstall]

Adds the hooks to ~/.claude/settings.json (after backing it up), adds the /talk command and switches
dictation to tap mode. Safe to run more than once. Run it with the project's .venv python."""
import argparse
import copy
import json
import shutil
import sys
from pathlib import Path

HOOK_MODULE = "talk.hooks"
COMMAND_MD = """---
description: Turn Claude reading its replies aloud on or off for this session
---
Reply with exactly this sentence and nothing else: "Talk mode isn't set up correctly. Check C:\\Users\\olodh\\Projects\\claude-talk\\logs\\talk.log."
"""


def _hook(python: str, event_arg: str, **extra) -> dict:
    return {"type": "command", "command": python, "args": ["-m", HOOK_MODULE, event_arg], **extra}


def _is_ours(group) -> bool:
    return isinstance(group, dict) and any(
        HOOK_MODULE in (hook.get("args") or []) for hook in group.get("hooks", []) if isinstance(hook, dict)
    )


def remove_from_settings(settings: dict) -> dict:
    result = copy.deepcopy(settings)
    hooks = result.get("hooks")
    if isinstance(hooks, dict):
        for event in list(hooks):
            kept = [group for group in hooks[event] if not _is_ours(group)]
            if kept:
                hooks[event] = kept
            else:
                del hooks[event]
        if not hooks:
            del result["hooks"]
    return result


def merge_settings(settings: dict, python: str) -> dict:
    result = remove_from_settings(settings)  # start clean so re-running never duplicates
    hooks = result.setdefault("hooks", {})
    ours = {
        "UserPromptSubmit": {"hooks": [_hook(python, "prompt", timeout=10)]},
        "UserPromptExpansion": {"matcher": "talk", "hooks": [_hook(python, "toggle", timeout=10)]},
        "Stop": {"hooks": [_hook(python, "stop", **{"async": True})]},
        "SessionEnd": {"hooks": [_hook(python, "session-end", timeout=10)]},
    }
    for event, group in ours.items():
        hooks.setdefault(event, []).append(group)
    voice = result.get("voice") if isinstance(result.get("voice"), dict) else {}
    result["voice"] = {**voice, "enabled": True, "mode": "tap"}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install or remove Claude Talk's Claude Code hooks.")
    parser.add_argument("--uninstall", action="store_true", help="remove the hooks and the /talk command")
    parser.add_argument("--claude-dir", default=str(Path.home() / ".claude"), help="Claude Code config folder")
    args = parser.parse_args(argv)

    claude_dir = Path(args.claude_dir)
    settings_path = claude_dir / "settings.json"
    command_path = claude_dir / "commands" / "talk.md"
    settings = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8-sig"))
        shutil.copy2(settings_path, settings_path.with_name("settings.json.bak-claude-talk"))

    if args.uninstall:
        new_settings = remove_from_settings(settings)
        command_path.unlink(missing_ok=True)
        print("Claude Talk removed. Dictation is left in its current mode.")
    else:
        new_settings = merge_settings(settings, sys.executable)
        command_path.parent.mkdir(parents=True, exist_ok=True)
        command_path.write_text(COMMAND_MD, encoding="utf-8")
        print(f"Claude Talk installed: hooks use {sys.executable}; /talk added; dictation set to tap mode.")

    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(new_settings, indent=2) + "\n", encoding="utf-8")
    print(f"Settings written to {settings_path} (backup: settings.json.bak-claude-talk)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Create `README.md`:

````markdown
# Claude Talk

Makes Claude Code read its replies aloud, so you can have a spoken conversation at your desk.

## Use it

1. In any Claude Code session, type `/talk`. You'll see "🔊 Talk mode on".
2. Tap **Space**, speak, then tap **Space** again to send (built-in tap dictation).
3. Claude replies on screen and reads out the gist. Code and long detail stay on screen.
4. Tap **Space** (to reply) or press **Esc** to cut Claude off.
5. Type `/talk` again to turn it off. Other sessions stay silent unless you turn them on.

## Settings

Edit `config.json`:

| Setting | Default | Meaning |
|---|---|---|
| `voice` | `en-GB-SoniaNeural` | Any Microsoft neural voice. List them with `.venv\Scripts\edge-tts.exe --list-voices` |
| `rate` | `+0%` | Speaking speed, e.g. `+15%` or `-10%` |
| `full_read_max_words` | `120` | Replies up to this many spoken words are read in full |
| `gist_max_words` | `60` | Longer replies: at most this many words of the opening paragraph |
| `fallback_to_windows_voice` | `true` | Use the built-in Windows voice if the online voice fails |

## Setup (once)

```powershell
cd C:\Users\olodh\Projects\claude-talk
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m talk.install
```

Then start a new Claude Code session. To remove it: `.venv\Scripts\python.exe -m talk.install --uninstall`.

## Good to know

- Spoken text (never code blocks) is sent to Microsoft's online voice service. This is an unofficial use of that service, so if it stops working, the Windows voice takes over.
- Space and Esc stop Claude talking anywhere in Windows while it speaks, including in other apps.
- Problems? Check `logs\talk.log`. Test the voice on its own with `.venv\Scripts\python.exe scripts\say.py "Hello"`.
- Tests: `.venv\Scripts\python.exe -m pytest` (add `$env:TALK_NETWORK_TESTS="1"` to include the online voice).
````

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest -v`
Expected: all tests pass (one network test skipped)

- [ ] **Step 5: Install for real**

```powershell
.venv\Scripts\python.exe -m talk.install
Get-Content $HOME\.claude\settings.json
```

Expected: the installer prints the two lines. `settings.json` now has `UserPromptSubmit`, `UserPromptExpansion`, `Stop` and `SessionEnd` entries pointing at `C:\Users\olodh\Projects\claude-talk\.venv\Scripts\python.exe`, plus `"voice": {"enabled": true, "mode": "tap"}`. All previous keys (`model`, `enabledPlugins`, `voiceEnabled`, etc.) are unchanged. `settings.json.bak-claude-talk` exists next to it.

- [ ] **Step 6: Commit**

```powershell
git add talk/install.py tests/test_install.py README.md
git commit -m "feat: add installer, /talk command and README" --trailer "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" --trailer "Claude-Session: https://claude.ai/code/session_01PynKPRx4DNyfD6UkLUSyJL"
```

---

### Task 10: End-to-end check with Omar

Done together with Omar in a real, interactive Claude Code session. Nothing here can be automated.

**Files:**
- Modify (only if a check fails as described): `talk/hooks.py` (`WAIT_FOR_SPEAKER`)
- Modify: `docs/superpowers/notes/2026-10-04-hook-probe.md` (append results)

- [ ] **Step 1: Omar opens a new Claude Code session** (any folder) and runs the five checks from the spec:

1. Type `/talk`. Expected: "🔊 Talk mode on…" and no reply from Claude. Then tap Space, ask a chatty question and tap Space. Expected: the whole reply is spoken within about 2 seconds of it appearing.
2. Ask for some build work, e.g. "Create a file hello.py that prints hello, then run it". Expected: you hear the gist, then "The rest is on screen."
3. Ask something with a long answer. Tap Space mid-speech. Expected: it stops at once and dictation starts.
4. Open a second Claude Code window without `/talk` and ask anything. Expected: silence.
5. Turn Wi-Fi off and ask something short in the talk session. Expected: about 5 seconds, then the Windows voice. Turn Wi-Fi back on.

Also: type `/talk` again and confirm "🔇 Talk mode off." and that the next reply is silent.

- [ ] **Step 2: If check 1 is silent, diagnose before changing anything**

Look at `logs\talk.log`:
- **No "speaking N words" line:** the Stop hook didn't run. Check `/hooks` in Claude Code lists the four Claude Talk hooks, and that the session was started after the install.
- **"speaking" is logged but there's no `speaker xxxxxxxx:` line, and no speaker process is running** (check with `Get-Process pythonw -ErrorAction SilentlyContinue`): the speaker was killed when the hook exited. Set `WAIT_FOR_SPEAKER = True` in `talk/hooks.py`, re-run `.venv\Scripts\python.exe -m pytest tests/test_hooks.py`, start a new Claude Code session and repeat check 1.
- **`/talk` went to Claude, which replied "Talk mode isn't set up correctly":** neither hook blocked the command. Check the log for `hook ['toggle'] failed` / `hook ['prompt'] failed` tracebacks and fix the cause.

- [ ] **Step 3: Record the results**

Append to `docs/superpowers/notes/2026-10-04-hook-probe.md`:

```markdown
## Interactive check (Task 10)
1. Chat reply spoken: pass/fail (notes)
2. Build gist + "rest is on screen": pass/fail
3. Space stops speech: pass/fail
4. Silent second session: pass/fail
5. Offline fallback voice: pass/fail
WAIT_FOR_SPEAKER: False/True (why)
```

- [ ] **Step 4: Commit**

```powershell
git add docs/superpowers/notes/2026-10-04-hook-probe.md talk/hooks.py
git commit -m "docs: record end-to-end check results" --trailer "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" --trailer "Claude-Session: https://claude.ai/code/session_01PynKPRx4DNyfD6UkLUSyJL"
```
