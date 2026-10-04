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
    assert Config().closing_max_words == 40
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
