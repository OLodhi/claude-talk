"""Register Claude Talk with Claude Code: python -m talk.install [--uninstall]

Adds the hooks to ~/.claude/settings.json (after backing it up), adds the /talk command and switches
dictation to tap mode. Safe to run more than once. Run it with the project's .venv python."""
import argparse
import copy
import json
import shutil
import sys
from pathlib import Path

from talk import paths

HOOK_MODULE = "talk.hooks"


def command_md() -> str:
    return f"""---
description: Turn Claude reading its replies aloud on or off for this session
disable-model-invocation: true
---
Reply with exactly this sentence and nothing else: "Talk mode isn't set up correctly. Check {paths.root() / 'logs' / 'talk.log'}."
"""


def _hook(python: str, event_arg: str, **extra) -> dict:
    return {"type": "command", "command": python, "args": ["-P", "-m", HOOK_MODULE, event_arg], **extra}


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
        command_path.write_text(command_md(), encoding="utf-8")
        print(f"Claude Talk installed: hooks use {sys.executable}; /talk added; dictation set to tap mode.")

    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(new_settings, indent=2) + "\n", encoding="utf-8")
    print(f"Settings written to {settings_path} (backup: settings.json.bak-claude-talk)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
