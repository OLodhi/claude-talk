# Claude Talk: Design

**Date:** 2026-10-04
**Status:** Draft, awaiting review
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
2. Conversational replies are read in full. Long or technical replies are summarised as the gist plus "The rest is on screen."
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

 Speaker process: reply → speakable text → edge-tts audio (sentence by sentence) → playback
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

### 6.2 File layout

```
C:\Users\olodh\Projects\claude-talk\
  talk\                     Python package (switch, speakable, speaker, control, hooks, config)
  tests\                    automated tests
  docs\superpowers\specs\   this document
  config.json               voice and length settings
  requirements.txt          edge-tts (+ test deps)
  README.md                 setup and usage
  .venv\                    project-only Python environment (not committed)
  state\                    session markers, current-speaker record (not committed)
  logs\                     talk.log (not committed)

C:\Users\olodh\.claude\commands\talk.md   makes /talk appear in autocomplete
C:\Users\olodh\.claude\settings.json      hook registrations added
```

Hooks call the project's own `.venv` Python, so nothing is installed into the global Python.

## 7. Component details

### 7.1 Switch: `/talk`

- `~/.claude/commands/talk.md` exists so `/talk` shows up in the command list. Its body is a harmless safety net: if the hook ever fails to intercept the command, Claude is told to reply only "Talk mode isn't set up correctly. Check `Projects\claude-talk\logs\talk.log`."
- A `UserPromptExpansion` hook with matcher `talk` intercepts the command and **blocks** it, so it never reaches Claude and costs no tokens. The block `reason` is the message the user sees.
- **The toggle:** if the session's marker `state/sessions/<session_id>` is absent, it's created and the reply is "🔊 Talk mode on: Claude will read replies aloud. Tap Space or Esc to stop it talking." If the marker is present, it's removed, any current speech is stopped, and the reply is "🔇 Talk mode off."
- **Health check when turning on:** the hook confirms `edge-tts` can be imported. If it can't, talk mode stays off and the message says how to fix setup.
- **Housekeeping:** when turning on, markers older than 7 days are deleted (they belong to sessions that ended without cleanup).
- **Fallback, if it turns out to be needed:** if blocking via `UserPromptExpansion` doesn't behave as documented, the same logic moves to `UserPromptSubmit`, which sees the raw `/talk` text before expansion. This is verified as the first build task.

### 7.2 Nudge

`UserPromptSubmit` hook. For every prompt:

1. If `prompt_source` is `user_input`, **stop any current speech** (you've moved on).
2. If this session's talk marker exists, return `additionalContext`:

> Talk mode is on: your reply will be read aloud to the user. Open with one or two plain sentences giving the gist, written the way you'd say it out loud. If the user is just chatting, keep the whole reply short and conversational. For technical work, put the details (code, file paths, lists) after the gist as usual; they stay on screen and won't be read out.

Sessions without the marker get no output, so their behaviour is unchanged.

### 7.3 Speaker launcher

`Stop` hook. If the session's marker exists and `last_assistant_message` is non-empty, it launches the Speaker as a **detached background process** (passing the reply text and the session id via a temp file) and exits immediately. The session is never kept waiting.

### 7.4 Turning a reply into speech (`speakable`)

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
- If nothing speakable remains (e.g. a code-only reply), say "Done. The details are on screen."

### 7.5 Speaker process

1. **Register as current speaker.** Write `state/speaker.json` (`pid`, `session_id`, start time). If another speaker is already registered, ask it to stop first, so only one voice plays at a time.
2. **Split into sentences** and synthesise them with `edge-tts` (voice and rate from config). Playback of sentence 1 starts as soon as its audio arrives, and later sentences are synthesised while earlier ones play.
3. **Play** each MP3 chunk with Windows' built-in media control interface (`winmm` via `ctypes`), so no extra audio libraries are needed.
4. **Watch for stop**, about every 50 ms during playback:
   - Space or Esc pressed (`GetAsyncKeyState`, counting only presses that begin after speech started).
   - A stop request in `state/stop` addressed to this speaker.

   Either one stops playback at once, cleans up temp files and exits.
5. **Fallback:** if `edge-tts` fails or the first audio takes more than 5 seconds, speak the remaining text with the Windows built-in voice (`System.Speech` in a PowerShell subprocess, which is killed if a stop arrives).
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
  "fallback_to_windows_voice": true
}
```

Missing keys fall back to these defaults, and a broken file falls back to all defaults (logged).

## 9. Errors and safety

- **Every hook exits 0 and never writes to stderr.** Any exception is caught and logged to `logs/talk.log` (capped at 1 MB, one backup). The only user-visible output is the `/talk` message and the nudge.
- Hooks do no network calls and no slow work inline. Synthesis happens only in the detached Speaker.
- **Key watching** reads only Space and Esc, only while speaking, and records nothing.
- **Privacy:** only the speakable text (never code blocks) is sent to Microsoft's TTS service. Dictation audio already goes to Anthropic under Claude Code's normal terms.

## 10. Setup (done once during the build)

1. Create `.venv` and install `requirements.txt`.
2. Add `~/.claude/commands/talk.md`.
3. Add the four hook registrations to `~/.claude/settings.json`, merged with the existing settings.
4. Switch dictation to tap mode: `"voice": {"enabled": true, "mode": "tap"}`.

## 11. Testing

**Automated** (pytest):
- `speakable`: a table of realistic replies (chat answers, build summaries, code-only replies, paths mid-sentence, links, nested lists, long first paragraphs) mapped to the exact expected spoken text.
- `switch`: on/off per session, isolation between sessions, stale-marker cleanup.
- `hooks`: each entry point given sample hook JSON. It must produce the right output, exit 0 and never raise, including on malformed input.
- `control`: start/stop with a fake speaker process. A second start replaces the first, and stop force-kills a speaker that doesn't respond.

**Manual check (about 5 minutes, by Omar):**
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
| Hook command quirks on Windows (shell, quoting) | Absolute paths, no spaces. Verified with a real session in the manual check. |
