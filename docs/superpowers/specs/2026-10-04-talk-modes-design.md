# Claude Talk: Speech Modes

**Date:** 2026-10-04
**Status:** Implemented
**Owner:** Omar Lodhi
**Builds on:** `2026-10-04-claude-talk-design.md` (the main spec; §-numbers below that say "main spec" refer to it)

## 1. Goal

Let the user choose how much of each reply Claude Talk reads aloud:

| Mode | What is spoken |
|---|---|
| `gist` | Today's behaviour: the opening, then "The remainder of details are on screen." and the closing paragraph (main spec §7.4) |
| `full` | Everything speakable in the reply, with no length limit |
| `summary` | A separate spoken summary that Claude writes at the end of the reply, instead of the on-screen text |

## 2. Decisions (confirmed with Omar)

| Topic | Decision |
|---|---|
| Choosing a mode | Per session with `/talk <mode>`, plus a default in `config.json` |
| Summary source | Claude writes it as a visible final line starting with 🔊. No delay and no extra cost. |
| Rejected: hidden summary | Both ways of hiding text in Markdown showed up in the terminal when tested on 2026-10-04: an HTML comment (`<!-- … -->`) and a link-reference definition (`[//]: # (…)`). |
| Rejected: separate summariser | Haiku via `claude -p` (hooks and MCP off) took 7.7 to 9.1 s per reply when measured, which is too slow for conversation. The direct API would be faster but needs an API key and is billed per call. |

## 3. Success criteria

1. `/talk summary`: only the 🔊 paragraph is spoken, and speech starts as quickly as it does today.
2. `/talk full`: a reply well over 120 words is read to the end, apart from code blocks and tables.
3. In summary mode, a reply without a 🔊 paragraph is read in gist mode instead, and the log says so.
4. A session keeps its mode until it changes or ends, and other sessions are unaffected.
5. `/talk` on its own behaves as it does today, using the default mode from `config.json`.

## 4. Non-goals

- Hiding the summary from the screen (see §2).
- A different voice or speed per mode.
- A `/talk off` command. `/talk` on its own still turns talk mode off.
- Reading code blocks or tables in full mode.

## 5. Commands

Claude Talk reads the word after `/talk`: `command_args` in the `UserPromptExpansion` payload, or the text after `/talk ` in a raw `UserPromptSubmit` prompt. It's compared as the first word, trimmed and lower-cased.

| Typed | Talk off | Talk on |
|---|---|---|
| `/talk` | Turn on in the default mode | Turn off |
| `/talk gist`, `/talk full`, `/talk summary` | Turn on in that mode | Switch to that mode and stay on |
| `/talk <anything else>` | Nothing changes | Nothing changes |

Messages, all shown as the `/talk` block reason:

- On, or switched: `🔊 Talk mode on (<mode>): <what is read>. Tap Space or Esc to stop it talking.` The `<what is read>` part is:
  - gist: "Claude will read the gist of each reply aloud"
  - full: "Claude will read whole replies aloud, except code"
  - summary: "Claude will read a short spoken summary of each reply"
- Off: `🔇 Talk mode off.` (unchanged)
- Unknown word: `⚠️ Unknown talk option "<word>". Use /talk, /talk gist, /talk full, /talk summary, /talk again or /talk speed 50-200.` (wording extended when speed and repeat were added)

`/talk <mode>` gives the same message whether talk was off or already on. So if one command reaches both hooks, the repeat changes nothing and shows the same text. `/talk` on its own keeps its existing `prompt_id` de-duplication (main spec §7.1). The health check (`edge-tts` importable) runs whenever a command would turn talk on.

The `/talk` command file gets `argument-hint: [gist|full|summary]` so autocomplete shows the choices. Its description becomes: "Turn reading replies aloud on or off, or pick a mode: gist, full or summary".

## 6. Storing the mode

- **Default:** `config.json` gets a `"mode"` key, defaulting to `"gist"`. Capitals and surrounding spaces are ignored, as with `/talk <mode>`. Any other value is ignored with a log warning, and `gist` is used.
- **Per session:** the session's marker file (`state/sessions/<session_id>`) holds the mode word when one was chosen with `/talk <mode>`. An empty marker, the result of `/talk` on its own, means "use the default". So changing `config.json` affects those sessions from their next reply.
- **Unchanged behaviour:**
  - The marker existing still means talk is on.
  - Refreshing the marker on each prompt keeps its contents.
  - Turning talk off deletes the marker, so the mode is forgotten with it.

## 7. The nudge for each mode

The `UserPromptSubmit` nudge (main spec §7.2) depends on the session's mode:

- **gist** (unchanged): "Talk mode is on: your reply will be read aloud to the user. Open with one or two plain sentences giving the gist, written the way you'd say it out loud. If the user is just chatting, keep the whole reply short and conversational. For technical work, put the details (code, file paths, lists) after the gist as usual; they stay on screen and won't be read out."
- **full**: "Talk mode is on (full mode): your whole reply will be read aloud to the user, except code blocks and tables. Write it the way you'd say it out loud, and keep it concise."
- **summary**: "Talk mode is on (summary mode): only a spoken summary of your reply is read aloud. Write your reply for the screen as usual, then end it with one final paragraph that starts with 🔊 and gives two to four short sentences written to be heard: the gist in plain words, no file paths, code or symbols, and any question you're asking the user."

## 8. What is spoken (`speakable`)

Two new pure functions sit beside `to_speech`. They use the same cleanup rules as main spec §7.4: code blocks, tables, HTML and URLs removed, file paths shortened, and so on.

- **`full_speech(markdown)`:** every speakable paragraph, joined in order, with no word limits. If nothing is speakable, it returns "Done. The details are on screen.", like `to_speech`.
- **`summary_speech(markdown)`:** finds the last paragraph that starts with 🔊, ignoring fenced code blocks, and returns its cleaned text without the emoji. If there's no such paragraph, it returns `None`. A paragraph counts if its first line, after leading spaces, begins with 🔊 (with or without the U+FE0F variation selector). The paragraph runs from that line to the next blank line, so a summary wrapped over several lines is kept whole.

The Stop hook picks the function from the session's mode:

| Mode | Spoken text |
|---|---|
| gist | `to_speech(reply, …limits from config)` (unchanged) |
| full | `full_speech(reply)` |
| summary | `summary_speech(reply)`. If that is `None`, it logs "no spoken summary; using gist" and uses `to_speech(reply, …)` |

In gist and full modes, a 🔊 paragraph that happens to be in the reply is read like any other text. Emoji are already dropped from speech.

## 9. Code changes

| File | Change |
|---|---|
| `talk/config.py` | `mode: str = "gist"`, with the value checked against the three modes |
| `talk/switch.py` | `turn_on(session_id, mode=None)` writes the mode when one is given and otherwise keeps the contents. `mode(session_id)` returns the stored mode, or `None` for "use the default". |
| `talk/hooks.py` | Parses the `/talk` argument, sends the per-mode messages and nudge, and chooses the speech in `handle_stop` |
| `talk/speakable.py` | `full_speech`, `summary_speech` |
| `talk/install.py` | New description and `argument-hint` in the `/talk` command file |
| `config.json` | `"mode": "gist"` |
| `README.md`, main spec | Modes, the `mode` setting and the new commands. Main spec §13 gets a change-log entry. |

## 10. Errors

- Hooks keep their rule (main spec §9): they always exit 0, never write to stderr, and log any exception.
- A missing 🔊 paragraph falls back to gist (§8).
- A bad `mode` in `config.json` falls back to `gist` (§6).
- An unknown word after `/talk` changes nothing and says which modes exist (§5).
- A marker holding an unknown word, for example one written by hand, is treated as "use the default".

## 11. Testing

Tests are written first (pytest):

- **`speakable`:**
  - `full_speech` reads a reply of more than 120 words to the end, still drops code blocks and tables, and returns the "nothing to say" text for a code-only reply.
  - `summary_speech` returns the last 🔊 paragraph, keeps a summary wrapped over two lines whole, ignores 🔊 inside a code block, cleans inline code and paths, and returns `None` when there's no 🔊 paragraph.
- **`switch`:**
  - The mode is stored and read back per session.
  - `/talk` on its own leaves an empty marker, which reads back as `None`.
  - Refreshing the marker keeps the mode.
  - Turning off forgets it.
- **`config`:** `mode` defaults to `gist`, and an invalid value falls back to `gist`.
- **`hooks`:**
  - `/talk summary` when off turns on in summary mode, and when on switches mode without turning off. Both cases give the same message.
  - `/talk` on its own still toggles.
  - An unknown word changes nothing and gives the warning.
  - The argument is read from both `command_args` and a raw prompt.
  - The nudge matches the mode.
  - `handle_stop` speaks the 🔊 paragraph in summary mode and falls back to gist when there isn't one.
  - Full mode speaks the whole reply.
  - A session with no stored mode follows `config.json`.
- **`install`:** the `/talk` file has the `argument-hint`.

**Manual check with Omar:**
1. `/talk full`: a long reply is read to the end.
2. `/talk summary`: only the 🔊 line is read.
3. `/talk gist`: today's behaviour.
4. `/talk sumary`: the warning appears.
5. `/talk`: talk turns off.
