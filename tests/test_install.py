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
