# Claude Talk: Design

**Date:** 2026-10-04
**Status:** Built and in use. Updated 2026-10-04 to match the code (see §13 for changes since the first build).
**Owner:** Omar Lodhi

## 1. Goal

Have a natural spoken conversation with Claude Code at the desk, like voice mode in the Claude mobile app. You speak, Claude answers on screen *and* out loud, and you can cut it off and reply without touching the keyboard beyond a single key.

## 2. Background

What Claude Code already provides (per the [voice dictation docs](https://code.claude.com/docs/en/voice-dictation)):

- **Voice input**: `/voice` dictation, transcribed by Anthropic and tuned for coding vocabulary.
- **Tap mode** (`/voice tap`): tap Space to start recording, tap again to stop. Transcripts of three or more words are sent automatically, so Enter isn't needed. Recording also stops after 15 seconds of silence.

What it does not provide:

- **No spoken replies.** Claude Code never reads its output aloud.
- **No phone voice mode.** The Claude app's voice mode is for Chat, and the docs don't say it works for Claude Code sessions.

Claude Talk therefore adds **only the missing half**: Claude speaking its replies. Input stays on the built-in tap-mode dictation.

## 3. Decisions (confirmed with Omar)

| Topic | Decision |
|---|---|
| Setting | At the desk, in the normal Claude Code terminal |
| Use | Both conversational (planning, discussing) and build work (code changes), about equally |
| Input | Built-in `/voice tap`: tap, speak, tap to send |
| Voice | Microsoft's free online neural voices (the Edge "Read Aloud" voices, via the `edge-tts` package). Accepted that reply text goes to Microsoft and that the service is unofficial. |
| When it speaks | Off by default; switched on per session with `/talk` |
| Approach | Add-on to the existing CLI via hooks (not a separate voice app) |

## 4. Success criteria

1. In a session with `/talk` on, Claude starts speaking within about 2 seconds of a reply finishing.
2. Conversational replies are read in full. Long or technical replies are summarised as the gist, then "The remainder of details are on screen." and the closing paragraph (or just "The rest is on screen." when there is no closing paragraph).
3. Tapping Space or pressing Esc while Claude is talking silences it immediately.
4. Sessions without `/talk` never speak, and only one voice ever plays at a time.
5. Nothing about Claude Talk can break, slow down or interrupt a Claude Code session.

## 5. Non-goals (this version)

- **Hands-free listening.** No always-on mic, pause detection or wake word.
- **Interrupting by voice.** You can't cut Claude off by starting to talk.
- **Speaking mid-task prompts.** Claude asking a multiple-choice question, permission prompts, and subagent or background output aren't spoken.
- **Phone / Remote Control use**, and macOS or Linux.
- **Choosing voices from inside Claude Code.** Voice choice is set in the config file.

## 6. Architecture

### 6.1 Components

```
                         ┌──────────────────────────┐
 you type /talk ───────► │ 1. Switch                │──► per-session on/off marker
                         │   (UserPromptExpansion)  │    + "🔊 Talk mode on/off"
                         └──────────────────────────┘
                         ┌──────────────────────────┐
 you send a message ───► │ 2. Nudge                 │──► adds "reply will be read aloud" note
                         │   (UserPromptSubmit)     │    to Claude's context (talk sessions only)
                         └──────────────────────────┘    + stops any current speech
                         ┌──────────────────────────┐
 Claude finishes ──────► │ 3. Speaker launcher      │──► starts detached Speaker process
                         │   (Stop)                 │
                         └──────────────────────────┘
                         ┌──────────────────────────┐
 session closes ───────► │ 4. Cleanup (SessionEnd)  │──► clears marker, stops its speech
                         └──────────────────────────┘

 Speaker process: reply → speakable text → edge-tts audio (all chunks requested at once) → playback
                  watches Space / Esc / stop requests → stops instantly
                  edge-tts unavailable → Windows built-in voice
```

Each unit has one job:

| Unit | Responsibility | Depends on |
|---|---|---|
| `switch` | Read, set and clear the per-session talk flag | file system |
| `speakable` | Turn a Markdown reply into the text to speak (pure function, no I/O) | config limits |
| `speaker` | Synthesise and play speech; obey stop requests and key presses; fall back to the Windows voice | `edge-tts`, Windows APIs |
| `control` | Start a speaker (replacing any current one); stop the current speaker | `speaker`, state files |
| `hooks` | Thin entry points: parse hook JSON from stdin, call the units above, never fail | all of the above |
| `config` | Load `config.json` with defaults | file system |
| `install` | Add or remove the hooks, the `/talk` command and tap mode in the Claude Code settings | file system |

### 6.2 File layout

```
claude-talk\                any folder (for example ~\Projects\claude-talk); nothing depends on where
  talk\                     Python package (switch, speakable, speaker, control, hooks, config, install, …)
  tests\                    automated tests
  docs\superpowers\         this spec, the original build plan, hook probe notes
  scripts\say.py            speak one line, to test the voice on its own
  setup.cmd, setup.ps1      one-step install and update (§10)
  config.json               voice and length settings
  pyproject.toml            package definition: edge-tts (+ pytest for development)
  README.md                 setup and usage
  .venv\                    project-only Python environment (not committed)
  state\                    session markers, current-speaker record (not committed)
  logs\                     talk.log (not committed)

~\.claude\commands\talk.md   makes /talk appear in autocomplete
~\.claude\settings.json      hook registrations added (previous version kept as settings.json.bak-claude-talk)
```

Hooks call the project's own `.venv` Python, so nothing is installed into the global Python. They are registered in exec form (the Python path plus an argument list, run with `-P`), so no shell or quoting is involved and the current folder can't shadow the `talk` package. Messages that mention files (the `/talk` safety net, the setup hint) name the folder Claude Talk is actually installed in.

## 7. Component details

### 7.1 Switch: `/talk`

- `~/.claude/commands/talk.md` exists so `/talk` shows up in the command list. Its body is a harmless safety net: if the hook ever fails to intercept the command, Claude is told to reply only "Talk mode isn't set up correctly. Check `<install folder>\logs\talk.log`." The command sets `disable-model-invocation: true`, so Claude can't run it by itself.
- A `UserPromptExpansion` hook with matcher `talk` intercepts the command and **blocks** it, so it never reaches Claude and costs no tokens. The block `reason` is the message the user sees.
- **The toggle:** if the session's marker `state/sessions/<session_id>` is absent, it's created and the reply is "🔊 Talk mode on (<mode>): …". See the speech modes spec (`2026-10-04-talk-modes-design.md`) for `/talk <mode>` and the exact wording. If the marker is present, it's removed, any current speech is stopped, and the reply is "🔇 Talk mode off."
- **Health check when turning on:** the hook confirms `edge-tts` can be imported. If it can't, talk mode stays off and the message says to run `setup.cmd` in the install folder to repair it.
- **Housekeeping:** when turning on, markers older than 7 days are deleted (they belong to sessions that ended without cleanup).
- **Belt and braces:** the `UserPromptSubmit` hook also recognises a raw `/talk` and toggles the same way, in case `UserPromptExpansion` doesn't behave as documented. Both hooks are registered. The toggle remembers the last `prompt_id` it handled, so one `/talk` seen by both hooks flips the switch only once. The first build task probes how both hooks actually behave.

### 7.2 Nudge

`UserPromptSubmit` hook. For every prompt:

1. If `prompt_source` is `user_input`, **stop any current speech** (you've moved on).
2. If this session's talk marker exists, return `additionalContext`:

> Talk mode is on: your reply will be read aloud to the user. Open with one or two plain sentences giving the gist, written the way you'd say it out loud. If the user is just chatting, keep the whole reply short and conversational. For technical work, put the details (code, file paths, lists) after the gist as usual; they stay on screen and won't be read out.

That is the gist-mode nudge; full and summary modes have their own (speech modes spec §7).

Sessions without the marker get no output, so their behaviour is unchanged.

### 7.3 Speaker launcher

`Stop` hook. If the session's marker exists and `last_assistant_message` is non-empty, it launches the Speaker as a **detached background process** (passing the reply text and the session id via a temp file) and exits immediately. The session is never kept waiting.

### 7.4 Turning a reply into speech (`speakable`)

This is gist mode, the default. Full and summary modes are described in `2026-10-04-talk-modes-design.md`.

A pure function from Markdown to plain text:

| In the reply | Spoken as |
|---|---|
| Paragraphs, bullet and numbered items | Sentences (list items get end punctuation if missing) |
| Fenced code blocks, tables, HTML, images, Mermaid/ASCII diagrams | Removed |
| `[text](url)` links | `text` |
| Bare URLs | Removed |
| Inline code of 3 words / 30 characters or less, e.g. `/voice tap` | Kept, backticks removed |
| Longer inline code | Removed |
| File paths, e.g. `src/auth/session.ts:42` | File name only: `session.ts` |
| Headings, bold/italic markers, blockquote markers, emoji | Dropped (heading lines removed entirely) |

The path rule is applied before the inline-code length rule, so `` `src/auth/session.ts:42` `` becomes `session.ts`.

**Length rule:**

- If the speakable text is `full_read_max_words` (default 120) or fewer, read it all.
- Otherwise read only the **first paragraph**, trimmed at a sentence boundary to `gist_max_words` (default 60), then add "The rest is on screen." The "first paragraph" is the first block of speakable text left after headings and removed elements are stripped. A run of consecutive list items counts as one paragraph.
- Then, if the reply ends in a prose paragraph of its own, read "The remainder of details are on screen." followed by that **closing paragraph** (the last speakable paragraph) instead of "The rest is on screen." Only its final sentences are kept: whole sentences, walking back from the last one, while the total stays within `closing_max_words` (default 40). If the last sentence alone is longer than that, there is no closing.
- No closing is read (the output ends with "The rest is on screen.") when the last paragraph is a list, ends with ":", or is already part of the gist, or when the reply does not end in prose (its last non-blank line, after removing code blocks, is a code block, table row, list item, heading or horizontal rule).
- If nothing speakable remains (e.g. a code-only reply), say "Done. The details are on screen."

### 7.5 Speaker process

1. **Registered as current speaker.** Before launching it, `control.start_speaking` stops any registered speaker, then records the new one in `state/speaker.json` (`pid`, a random `token`, `session_id`, start time). So only one voice plays at a time.
2. **Split into chunks and synthesise** with `edge-tts` (voice and rate from config). The first sentence is a chunk of its own so speech starts fast. The remaining sentences are grouped into chunks of up to 250 characters.
   - **All chunks are requested at once** when speaking starts, so later chunks are ready by the time earlier ones finish playing. Chunks play in order.
   - **Backup request:** a chunk still missing after 1 second (`BACKUP_AFTER`) gets a second identical request. The first successful result is played, and a failed backup never replaces a slow success. Measurements showed the service usually answers in about 0.4 s but stalls for 2 to 5 s on about 1 request in 4, independently per request. Requesting chunks one after another let a stalled second chunk leave an audible pause after the first sentence.
3. **Play** each MP3 chunk with Windows' built-in media control interface (`winmm` via `ctypes`), so no extra audio libraries are needed.
4. **Watch for stop**, about every 50 ms during playback:
   - Space or Esc pressed (`GetAsyncKeyState`, counting only presses that begin after speech started).
   - A stop request in `state/stop` naming this speaker's token, or a newer speaker taking over `state/speaker.json`.

   Either one stops playback at once, cleans up temp files and exits.
5. **Fallback:** if `edge-tts` fails, the first chunk takes more than 5 seconds, a later chunk isn't ready within 15 seconds of being needed, or playback fails, speak the remaining text with the Windows built-in voice (`System.Speech` in a PowerShell subprocess, which is killed if a stop arrives).
6. **On exit:** remove `state/speaker.json` if it still names this process.

**Stopping (`control.stop`):** write a stop request, wait up to 500 ms for the speaker to exit, then force-kill the recorded process (and any fallback child) if it's still running. All stop triggers (the next prompt, `/talk` off, a new speaker, `SessionEnd`) go through this one function.

### 7.6 Cleanup

`SessionEnd` hook: delete the session's marker, and stop speech if the current speaker belongs to that session.

## 8. Configuration (`config.json`)

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

Missing keys fall back to these defaults, and a broken file falls back to all defaults (logged).

## 9. Errors and safety

- **Every hook exits 0 and never writes to stderr.** Any exception is caught and logged to `logs/talk.log` (capped at 1 MB, one backup). The only user-visible output is the `/talk` message and the nudge.
- Hooks do no network calls and no slow work inline. Synthesis happens only in the detached Speaker.
- **Key watching** reads only Space and Esc, only while speaking, and records nothing.
- **Privacy:** only the speakable text (never code blocks) is sent to Microsoft's TTS service. Dictation audio already goes to Anthropic under Claude Code's normal terms.

## 10. Setup and updates (`setup.cmd`)

Claude Talk lives in the private GitHub repo `OLodhi/claude-talk`. On any Windows PC with Git and Claude Code: clone it, then run `setup.cmd` (double-click, or `.\setup.cmd` in a terminal). `setup.cmd` runs `setup.ps1` with PowerShell's script policy bypassed. It:

1. **Finds Python 3.13**: through the `py` launcher, then the usual install folders. If it's missing, it installs it with `winget` (or, without winget, says to install it from python.org).
2. **Creates `.venv`** in the project folder, unless one already exists.
3. **Installs Claude Talk into `.venv`** as an editable install (`pip install -e`), so the hooks run the code in the folder and `git pull` updates them.
4. **Runs `python -P -m talk.install`**, which backs up `~/.claude/settings.json` to `settings.json.bak-claude-talk`, merges in the four hook registrations (replacing any earlier Claude Talk ones), writes `~/.claude/commands/talk.md`, and switches dictation to tap mode: `"voice": {"enabled": true, "mode": "tap"}`.

Setup is safe to run again, so **updating is `git pull` followed by `setup.cmd`**. To remove Claude Talk: `.venv\Scripts\python.exe -m talk.install --uninstall` (removes only Claude Talk's hooks and `/talk`, and leaves dictation as it is). `setup.ps1 -ClaudeDir <folder>` installs into a different Claude Code folder, which the tests use.

## 11. Testing

**Automated** (pytest):
- `speakable`: a table of realistic replies (chat answers, build summaries, code-only replies, paths mid-sentence, links, nested lists, long first paragraphs) mapped to the exact expected spoken text.
- `switch`: on/off per session, isolation between sessions, stale-marker cleanup.
- `hooks`: each entry point given sample hook JSON. It must produce the right output, exit 0 and never raise, including on malformed input.
- `control`: start/stop with a fake speaker process. A second start replaces the first, and stop force-kills a speaker that doesn't respond.
- `speaker`: fake synthesis and playback. Chunks play in order, failures and timeouts fall back with the remaining text, stops are obeyed, every chunk is requested straight away, a slow request gets a backup, a fast one doesn't, and a failed backup never beats a slow success.
- `install`: merging is idempotent and keeps other settings and hooks, uninstall removes only Claude Talk's, and the `/talk` file names the install folder.
- **Online tests** (only with `TALK_NETWORK_TESTS=1`): a real `edge-tts` synthesis, and a full `setup.cmd` run on a copy of the project against a scratch Claude Code folder. That run is done twice to show re-running is safe.

**Manual check (about 5 minutes, by Omar).** Results are recorded in `docs/superpowers/notes/2026-10-04-hook-probe.md` under "Interactive check".
1. `/talk` on, ask a chatty question: the whole reply is spoken.
2. Ask for build work: you hear the gist, then "The rest is on screen."
3. Tap Space mid-speech: it stops at once.
4. A second window without `/talk` stays silent.
5. Wi-Fi off: the Windows built-in voice speaks instead.

## 12. Risks

| Risk | Mitigation |
|---|---|
| Microsoft changes or blocks the unofficial TTS endpoint | Automatic Windows-voice fallback. Synthesis sits behind one function, so swapping provider (e.g. OpenAI TTS) is a contained change. |
| `/talk` blocking via `UserPromptExpansion` doesn't work as documented | Verified first. Fallback to `UserPromptSubmit`. |
| Claude ignores the nudge and writes long replies | The length rule caps what's spoken regardless. |
| Space typed in another app silences Claude | Accepted trade-off. |
| Hook command quirks on Windows (shell, quoting) | Exec-form hooks with absolute paths, so no shell is involved. Verified with a real session in the manual check. |
| The online voice stalls for seconds on some requests | All chunks requested at once, plus a backup request after 1 s (§7.5). The Windows voice takes over if the first audio needs more than 5 s. |
| Setup on a PC without Python | `setup.ps1` installs Python 3.13 with winget. This path hasn't been run yet, because the test PC already had Python. |

## 13. Changes since the first build

All on 2026-10-04:

- **Closing paragraph** (`e2141d3`): long replies read the gist, then "The remainder of details are on screen." and the closing paragraph, after feedback from the interactive check.
- **Portable install** (`f76f143`): `setup.cmd`/`setup.ps1`, no hardcoded folder paths, and the repo moved to private GitHub (`OLodhi/claude-talk`) so another PC can install and update it.
- **No pause after the first sentence** (`be70eed`): all chunks are requested at once, and slow requests get a backup (§7.5).
- **Speech modes**: `/talk gist|full|summary`, a `mode` default in `config.json`, and a 🔊 summary line in summary mode (`2026-10-04-talk-modes-design.md`).
