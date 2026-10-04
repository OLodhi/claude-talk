import pytest

from talk import paths, speed


@pytest.mark.parametrize("given, expected", [
    ("150", 150.0), ("150%", 150.0), (" 120 ", 120.0), ("87.5", 87.5),
    ("fast", None), ("", None), ("nan", None), ("inf", None),
])
def test_parse(given, expected):
    assert speed.parse(given) == expected


@pytest.mark.parametrize("given, expected", [(250, 200), (30, 50), (125.4, 125), (1.5, 50), (100, 100)])
def test_clamp_to_what_the_voice_can_do(given, expected):
    assert speed.clamp(given) == expected


@pytest.mark.parametrize("percent, rate", [(100, "+0%"), (150, "+50%"), (80, "-20%"), (200, "+100%"), (50, "-50%")])
def test_to_rate(percent, rate):
    assert speed.to_rate(percent) == rate


def test_nothing_saved_yet():
    assert speed.load() is None


def test_saved_speed_is_read_back():
    speed.save(120)
    assert speed.load() == 120


@pytest.mark.parametrize("content", ["abc", "999", ""])
def test_unreadable_or_out_of_range_file_is_ignored(content):
    (paths.state_dir() / "speed").write_text(content, encoding="utf-8")
    assert speed.load() is None


def test_current_prefers_the_saved_speed():
    speed.save(150)
    assert speed.current("+15%") == 150


@pytest.mark.parametrize("rate, expected", [("+15%", 115), ("-20%", 80), ("+0%", 100), ("weird", 100)])
def test_current_falls_back_to_the_config_rate(rate, expected):
    assert speed.current(rate) == expected
