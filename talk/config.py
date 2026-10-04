"""Settings from config.json in the Claude Talk folder. Anything missing or broken falls back to defaults."""
import json
from dataclasses import dataclass, fields, replace

from talk import paths
from talk.log import get_logger

MODES = ("gist", "full", "summary")


@dataclass(frozen=True)
class Config:
    voice: str = "en-GB-SoniaNeural"
    rate: str = "+0%"
    full_read_max_words: int = 120
    gist_max_words: int = 60
    closing_max_words: int = 40
    fallback_to_windows_voice: bool = True
    mode: str = "gist"


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
        if type(value) is not type(default):
            get_logger().warning(
                "Ignoring config.json %s=%r: expected %s", field.name, value, type(default).__name__
            )
        elif field.name == "mode" and value not in MODES:
            get_logger().warning("Ignoring config.json mode=%r: expected one of %s", value, ", ".join(MODES))
        else:
            values[field.name] = value
    return replace(defaults, **values)
