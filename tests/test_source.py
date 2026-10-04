import unicodedata
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "talk"


def _invisible(ch: str) -> bool:
    return unicodedata.category(ch) == "Cf" or 0xFE00 <= ord(ch) <= 0xFE0F  # format chars, variation selectors


def test_code_has_no_invisible_characters():
    """Invisible characters can't be reviewed and editors strip them silently; write them as escapes.
    (A stripped U+FE0F in the summary pattern would turn "🔊\ufe0f?" into "🔊?" and match every line.)"""
    found = [
        f"{path.name}:{number}"
        for path in sorted(PACKAGE.glob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if any(_invisible(ch) for ch in line)
    ]
    assert found == []
