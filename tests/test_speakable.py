import pytest

from talk.speakable import NOTHING_TO_SAY, REST_ON_SCREEN, speech_chunks, split_sentences, to_speech

LONG_LIST = "\n".join(
    f"- Updated module number {i} so that it uses the new helper consistently" for i in range(12)
)
BUILD_REPLY = (
    "I've fixed the login bug. The session token was expiring before the refresh ran, "
    "and the tests pass now.\n\n## Changes\n\n" + LONG_LIST + "\n\n```ts\nconst x = 1;\n```\n"
)
TEN_WORDS = "This sentence has exactly ten words in it right here."
HUGE_SENTENCE = " ".join(["word"] * 80) + "."

CASES = [
    ("plain chat",
     "Supabase is the better fit here. It gives you Postgres, auth and storage in one place.",
     "Supabase is the better fit here. It gives you Postgres, auth and storage in one place."),
    ("code only", "```python\nprint('hi')\n```", NOTHING_TO_SAY),
    ("link", "See [the docs](https://example.com/docs) for more.", "See the docs for more."),
    ("bare url", "Docs live at https://code.claude.com/docs/en/hooks today.", "Docs live at today."),
    ("short inline code", "Run `/voice tap` to switch.", "Run /voice tap to switch."),
    ("long inline code", "Then run `npm install --save-dev @types/node typescript` again.", "Then run again."),
    ("paths in inline code", "I changed `src/auth/session.ts:42` and `README.md`.",
     "I changed session.ts and README.md."),
    ("windows path in text", r"Edited C:\Users\olodh\Projects\claude-talk\config.json just now.",
     "Edited config.json just now."),
    ("unix path in text", "See /home/omar/app/src/main.py:10 for it.", "See main.py for it."),
    ("headings bold emoji", "## Summary\n\n**All tests pass** ✅\n\nNext I'll *tidy up* the docs.",
     "All tests pass. Next I'll tidy up the docs."),
    ("intro then list", "Changes:\n- Moved the refresh check\n- Added a test",
     "Changes: Moved the refresh check. Added a test."),
    ("table", "Here's the comparison:\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nB wins.",
     "Here's the comparison: B wins."),
    ("diagram fence", "```mermaid\ngraph TD\n  A-->B\n```\nDiagram above.", "Diagram above."),
    ("unterminated fence", "Here it is:\n```python\nprint(1)\n", "Here it is:"),
    ("snake_case kept", "The set_voice function handles it.", "The set_voice function handles it."),
    ("arrow", "Python 3.12 → 3.13 works.", "Python 3.12 to 3.13 works."),
    ("blockquote", "> Note: this is quoted.", "Note: this is quoted."),
    ("checkbox list", "- [x] Write tests\n- [ ] Ship it", "Write tests. Ship it."),
    ("html tag", "Use <kbd>Space</kbd> to talk.", "Use Space to talk."),
    ("non-ascii kept", "It costs £5 — that's fine.", "It costs £5 — that's fine."),
    ("empty list item dropped", "- `npm install --save-dev @types/node typescript`\n- Done", "Done."),
    ("windows line endings", "First line here.\r\n\r\nSecond line here.", "First line here. Second line here."),
    ("comparison symbols kept", "Use a < b && c > d carefully.", "Use a < b && c > d carefully."),
    ("long build reply gives gist only", BUILD_REPLY,
     "I've fixed the login bug. The session token was expiring before the refresh ran, "
     "and the tests pass now. " + REST_ON_SCREEN),
    ("long first paragraph trimmed at a sentence", " ".join([TEN_WORDS] * 8) + "\n\n" + LONG_LIST,
     " ".join([TEN_WORDS] * 6) + " " + REST_ON_SCREEN),
    ("huge first sentence cut", HUGE_SENTENCE + "\n\n" + LONG_LIST,
     " ".join(["word"] * 60) + "… " + REST_ON_SCREEN),
    ("bold label then gist", "**Summary**\n\nThe build passes now. I fixed three things.\n\n" + LONG_LIST,
     "The build passes now. I fixed three things. " + REST_ON_SCREEN),
    ("colon intro joins its list", "Here's what I changed:\n\n" + LONG_LIST,
     "Here's what I changed: "
     + " ".join(f"Updated module number {i} so that it uses the new helper consistently." for i in range(4))
     + " " + REST_ON_SCREEN),
]


@pytest.mark.parametrize("given,expected", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_to_speech(given, expected):
    assert to_speech(given) == expected


def test_limits_are_configurable():
    reply = "One two three four five. Six seven eight nine ten.\n\nEleven twelve."
    assert to_speech(reply, full_read_max_words=100) == "One two three four five. Six seven eight nine ten. Eleven twelve."
    assert to_speech(reply, full_read_max_words=5, gist_max_words=5) == "One two three four five. " + REST_ON_SCREEN


def test_split_sentences_does_not_split_file_names():
    assert split_sentences("a.ts is fine. Next one!") == ["a.ts is fine.", "Next one!"]


def test_speech_chunks_start_with_the_first_sentence_alone():
    sentences = " ".join(f"Sentence number {i} is here." for i in range(20))
    chunks = speech_chunks("One. " + sentences)
    assert chunks[0] == "One."
    assert all(len(chunk) <= 250 for chunk in chunks)
    assert " ".join(chunks) == "One. " + sentences


def test_speech_chunks_of_nothing():
    assert speech_chunks("") == []
