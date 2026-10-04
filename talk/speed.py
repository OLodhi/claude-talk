"""Playback speed chosen with /talk speed <percent>, kept in state/speed for every session.

100 is normal speed and 200 is twice as fast. Microsoft's voice only goes from half speed to double:
measured on 2026-10-04, asking for more than +100% still gives 2x."""
import math
import re

from talk import paths

MIN_PERCENT = 50
MAX_PERCENT = 200
_RATE = re.compile(r"^([+-]\d+)%$")


def _file():
    return paths.state_dir() / "speed"


def parse(text: str) -> float | None:
    """A typed speed such as "150" or "150%", or None if it isn't a number."""
    try:
        value = float(text.strip().rstrip("%").strip())
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def clamp(percent: float) -> int:
    return int(min(MAX_PERCENT, max(MIN_PERCENT, round(percent))))


def to_rate(percent: int) -> str:
    """edge-tts rate text: 150 -> "+50%", 80 -> "-20%"."""
    return f"{percent - 100:+d}%"


def save(percent: int) -> None:
    _file().write_text(str(percent), encoding="utf-8")


def load() -> int | None:
    try:
        value = int(_file().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return value if MIN_PERCENT <= value <= MAX_PERCENT else None


def current(config_rate: str) -> int:
    """The speed in use: the saved one, else config.json's rate (e.g. "+15%" -> 115), else 100."""
    saved = load()
    if saved is not None:
        return saved
    match = _RATE.match(config_rate.strip())
    return 100 + int(match.group(1)) if match else 100
