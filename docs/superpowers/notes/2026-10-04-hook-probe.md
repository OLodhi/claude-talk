# Hook probe findings (2026-10-04, Claude Code 2.1.289)

Run with `claude -p ... --settings probe/probe-settings.json --model haiku` from `probe/` (a project with `.claude/commands/talk.md`). Python launcher `C:\WINDOWS\py.exe -3.13`. Payloads below are verbatim except that long paths are shortened to `...`; every field name is kept.

Console output:
- Probe A (`/talk`, `PROBE_MODE=""`): `UserPromptExpansion operation blocked by hook:` / `probe: blocked in UserPromptExpansion` / `Original prompt: /talk`. `PROBE-EXPANDED` was not printed.
- Probe B (`/talk`, `PROBE_MODE="block-submit"`): identical output to A.
- Probe C (`Reply with the single word pong.`): `pong`.

Q1. In UserPromptSubmit, which field holds the typed text, and is it the raw "/talk"? → The field is `prompt`. In `-p` mode, UserPromptSubmit did not fire at all for `/talk` (probes A and B logged no UserPromptSubmit event), so the raw "/talk" was never observed in that event. It fired for the plain prompt in probe C:
```json
{"session_id":"dc50a428-...","transcript_path":"C:\\Users\\olodh\\.claude\\projects\\...\\dc50a428-....jsonl","cwd":"C:\\Users\\olodh\\Projects\\claude-talk\\probe","prompt_id":"40654408-11c4-4a58-8b7f-5f0b01dd4096","permission_mode":"default","hook_event_name":"UserPromptSubmit","prompt":"Reply with the single word pong."}
```
Caveat: this is `-p` behaviour. Whether an interactive `/talk` reaches UserPromptSubmit is untested here; Task 10 should check.

Q2. When UserPromptSubmit blocked "/talk" (probe B), did UserPromptExpansion still fire? → Inconclusive as framed. UserPromptSubmit never fired for `/talk`, so it never blocked anything. UserPromptExpansion fired in both A and B and blocked the command. For slash commands, UserPromptExpansion is the hook that sees `/talk`.

Q3. Did UserPromptExpansion fire for "/talk" with matcher "talk", and did its block stop the model (probe A)? Field names? Is prompt_id present in both events? → Yes, it fired and its block stopped the model: `claude` printed the block message and not `PROBE-EXPANDED`. `prompt_id` is present in UserPromptExpansion, UserPromptSubmit, Stop and SessionEnd. The same-turn comparison (UserPromptSubmit versus UserPromptExpansion on one prompt) was not possible because UserPromptSubmit does not fire for `/talk` in `-p` mode.
```json
{"session_id":"0ffeaa8c-59ec-46e8-8427-51633cfcd6a3","transcript_path":"C:\\Users\\olodh\\.claude\\projects\\...\\0ffeaa8c-....jsonl","cwd":"C:\\Users\\olodh\\Projects\\claude-talk\\probe","prompt_id":"a0b35348-9417-49db-beb0-3a53994b37a4","permission_mode":"default","hook_event_name":"UserPromptExpansion","expansion_type":"slash_command","command_name":"talk","command_args":"","command_source":"projectSettings","prompt":"/talk"}
```

Q4. Does the Stop payload include last_assistant_message? → Yes (`"pong"`):
```json
{"session_id":"dc50a428-...","transcript_path":"C:\\Users\\olodh\\.claude\\projects\\...\\dc50a428-....jsonl","cwd":"C:\\Users\\olodh\\Projects\\claude-talk\\probe","prompt_id":"40654408-11c4-4a58-8b7f-5f0b01dd4096","permission_mode":"default","hook_event_name":"Stop","stop_hook_active":false,"last_assistant_message":"pong","background_tasks":[],"session_crons":[]}
```

Q5. Did the detached child survive (child_survived.txt exists)? Spawned with breakaway or not? → Yes. `Test-Path .\child_survived.txt` printed `True` after 8 s, and the log recorded `{"event": "Stop-child", "spawned": "breakaway"}`. This was an async Stop hook in `-p` mode, so the detached child outlived both the hook and the CLI.

Q6. Did SessionEnd fire in -p mode, and with which fields? → Only for the blocked-command sessions (A, B; reason "other"); not after the normal turn (C). No SessionEnd line was logged for probe C's normal (non-blocked) session, even after the 8 s wait. Cause not determined (possibly the CLI exits before the hook runs after a normal turn); do not rely on SessionEnd in `-p` mode. Its fields:
```json
{"session_id":"0ffeaa8c-...","transcript_path":"C:\\Users\\olodh\\.claude\\projects\\...\\0ffeaa8c-....jsonl","cwd":"C:\\Users\\olodh\\Projects\\claude-talk\\probe","prompt_id":"a0b35348-9417-49db-beb0-3a53994b37a4","hook_event_name":"SessionEnd","reason":"other"}
```

Decisions:
- PROMPT_FIELDS = ("prompt", "user_prompt")  (the observed field is `prompt`; `user_prompt` is kept as a harmless fallback, as the plan specifies.)
- WAIT_FOR_SPEAKER = False  (the probe was a single async Stop hook spawning one breakaway child in `-p` mode, which is not interactive-mode evidence. Task 10 must still re-check speaker survival in an interactive session.)

Open questions for Task 10:
- Interactive mode: does UserPromptSubmit see a raw /talk, and if both hooks fire for one /talk, does prompt_id de-duplicate them?

Decision-rule check:
- Probe A and B both blocked `/talk` (neither printed `PROBE-EXPANDED`), so the "stop and report" rule does not trigger. UserPromptExpansion is the blocking hook that works; UserPromptSubmit blocking for `/talk` is unproven in `-p` mode.
- Q4 has `last_assistant_message`, so no transcript fallback is needed.
- `prompt_id` is present in every event seen.

## Interactive check (Task 10)

Run by Omar in a fresh interactive Claude Code session on 2026-10-04.

- Overall: "working pretty well". `/talk` toggled, and replies were spoken in the talk session.
- Feedback: long replies should also read the closing paragraph, which led to Change A (commit e2141d3). Long replies now say the gist, then "The remainder of details are on screen.", then the closing question or offer.
- Checks 3 (Space interrupts) and 5 (offline fallback voice) were not reported individually. Omar chose to merge. Both paths were verified earlier through logs (Task 7: `: stopped`, `: fallback`).
- WAIT_FOR_SPEAKER: stays False, because speech played in the interactive session, so the detached speaker survives the Stop hook.
- Still unverified interactively: whether UserPromptSubmit sees a raw `/talk`, and whether a `prompt_source` field is present. Both are harmless either way (see rulings R6, R18).
