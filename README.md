# Claude Talk

Makes Claude Code read its replies aloud, so you can have a spoken conversation at your desk.

## Use it

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

### Speed and repeat

| Type | What it does |
|---|---|
| `/talk speed 150` | Speaking speed as a percentage of normal: `100` is normal, `200` is twice as fast (the fastest the voice goes), `50` is half speed. Remembered across all sessions. |
| `/talk speed` | Tells you the current speed |
| `/talk again` (or `/talk repeat`) | Reads Claude's last spoken reply once more, at the current speed |

## Settings

Edit `config.json`:

| Setting | Default | Meaning |
|---|---|---|
| `voice` | `en-GB-SoniaNeural` | Any Microsoft neural voice. List them with `.venv\Scripts\edge-tts.exe --list-voices` |
| `mode` | `gist` | Mode used by `/talk` on its own: `gist`, `full` or `summary` |
| `rate` | `+0%` | Speaking speed, e.g. `+15%` or `-10%`. Once you use `/talk speed`, that takes over. |
| `full_read_max_words` | `120` | Replies up to this many spoken words are read in full |
| `gist_max_words` | `60` | Longer replies: at most this many words of the opening paragraph |
| `closing_max_words` | `40` | Longer replies: at most this many words of the closing paragraph, read after "The remainder of details are on screen." |
| `fallback_to_windows_voice` | `true` | Use the built-in Windows voice if the online voice fails |

## Set up on a PC

Works on Windows with Claude Code installed. You need Git and an internet connection; if Python 3.13 is missing, setup installs it with winget.

```powershell
mkdir $HOME\Projects -Force | Out-Null
cd $HOME\Projects
git clone https://github.com/OLodhi/claude-talk.git
cd claude-talk
.\setup.cmd
```

(Or double-click `setup.cmd` in the folder.) Then start a new Claude Code session and type `/talk`.

Setup adds the hooks to `~\.claude\settings.json` (backing it up to `settings.json.bak-claude-talk` first), adds the `/talk` command and switches dictation to tap mode. The hooks point at this folder, so leave it where it is; if you move it, delete its `.venv` folder and run `setup.cmd` again.

**Update:** `git pull`, then run `setup.cmd` again. (`config.json` is part of the repo. If `git pull` refuses because you've changed it, run `git stash`, then `git pull`, then `git stash pop` to keep your settings.)

**Remove:** `.venv\Scripts\python.exe -m talk.install --uninstall`

## Good to know

- Spoken text (never code blocks) is sent to Microsoft's online voice service. This is an unofficial use of that service, so if it stops working, the Windows voice takes over.
- The voice service sometimes stalls for a few seconds, so any block of speech not back within 1 second is requested a second time, and whichever copy arrives first is played. Microsoft may therefore receive some text twice.
- Space and Esc stop Claude talking anywhere in Windows while it speaks, including in other apps.
- Problems? Check `logs\talk.log`. Test the voice on its own with `.venv\Scripts\python.exe scripts\say.py "Hello"`.
- `/clear` starts a fresh session, so talk mode switches off; type `/talk` again.
- Tests: install the test tools once with `.venv\Scripts\python.exe -m pip install -e ".[dev]"`, then run `.venv\Scripts\python.exe -m pytest`. Add `$env:TALK_NETWORK_TESTS="1"` to include the online tests (the voice service and a full run of `setup.cmd`).
