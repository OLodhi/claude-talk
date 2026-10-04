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
