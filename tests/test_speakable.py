import pytest

from talk.speakable import (
    DETAILS_ON_SCREEN, NOTHING_TO_SAY, REST_ON_SCREEN, full_speech, speech_chunks, split_sentences, summary_speech,
    to_speech,
)

LONG_LIST = "\n".join(
    f"- Updated module number {i} so that it uses the new helper consistently" for i in range(12)
)
BUILD_REPLY = (
    "I've fixed the login bug. The session token was expiring before the refresh ran, "
    "and the tests pass now.\n\n## Changes\n\n" + LONG_LIST + "\n\n```ts\nconst x = 1;\n```\n"
)
TEN_WORDS = "This sentence has exactly ten words in it right here."
HUGE_SENTENCE = " ".join(["word"] * 80) + "."

JOB_REPLY = (
    "Give it about a week from when you applied. The system has both follow-ups set for 10 October, "
    "but that's a Saturday, so I'd send them on Monday the 12th.\n\n"
    "- **Cadence**: your follow-up settings allow one message 7 days after applying and, if there's still "
    "no reply, a second one 7 days later. Two is the limit; after that, leave it.\n"
    "- **Who to contact**: you applied to both through their own job systems (TXP's HiBob site and Kainos's "
    "Workday), and the tracker has no recruiter or hiring manager listed for either. Following up through those "
    "systems usually goes nowhere, so a short note to a named recruiter on LinkedIn will work better.\n"
    "- **Kainos**: the role was posted on 28 September, so they're probably still collecting applications. "
    "A week of silence is normal for a large consultancy.\n"
    "- **TXP**: the posting has been up since 19 July, so they may be further along or just slow. "
    "Either way, the same timing applies.\n\n"
    "If you want, I can find the right recruiter at each company and draft short follow-up messages so "
    "they're ready to send on Monday."
)

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
    ("closing paragraph is read after the bridge", JOB_REPLY,
     "Give it about a week from when you applied. The system has both follow-ups set for 10 October, "
     "but that's a Saturday, so I'd send them on Monday the 12th. " + DETAILS_ON_SCREEN
     + " If you want, I can find the right recruiter at each company and draft short follow-up messages so "
     "they're ready to send on Monday."),
    ("closing before a table is not read",
     "Gist sentence for this reply.\n\n" + LONG_LIST + "\n\nHere is the comparison.\n\n| A | B |\n|---|---|\n| 1 | 2 |",
     "Gist sentence for this reply. " + REST_ON_SCREEN),
    ("closing ending in a colon is not read",
     "Gist sentence for this reply.\n\n" + LONG_LIST + "\n\nRun this to check:\n\n```\npytest\n```",
     "Gist sentence for this reply. " + REST_ON_SCREEN),
    ("single long paragraph gives gist only", " ".join([TEN_WORDS] * 13),
     " ".join([TEN_WORDS] * 6) + " " + REST_ON_SCREEN),
]


@pytest.mark.parametrize("given,expected", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_to_speech(given, expected):
    assert to_speech(given) == expected


def test_limits_are_configurable():
    reply = "One two three four five. Six seven eight nine ten.\n\nEleven twelve."
    assert to_speech(reply, full_read_max_words=100) == "One two three four five. Six seven eight nine ten. Eleven twelve."
    assert to_speech(reply, full_read_max_words=5, gist_max_words=5) == (
        "One two three four five. " + DETAILS_ON_SCREEN + " Eleven twelve."
    )


def test_closing_keeps_its_final_sentences():
    reply = (
        "Gist sentence for this reply.\n\n" + LONG_LIST
        + "\n\nI also tidied the imports and renamed two helpers so the names match what they do now. "
        "The old names are gone everywhere. Want me to open a pull request?"
    )
    assert to_speech(reply) == (
        "Gist sentence for this reply. " + DETAILS_ON_SCREEN
        + " I also tidied the imports and renamed two helpers so the names match what they do now. "
        "The old names are gone everywhere. Want me to open a pull request?"
    )
    assert to_speech(reply, closing_max_words=15) == (
        "Gist sentence for this reply. " + DETAILS_ON_SCREEN
        + " The old names are gone everywhere. Want me to open a pull request?"
    )
    assert to_speech(reply, closing_max_words=5) == "Gist sentence for this reply. " + REST_ON_SCREEN


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


LONG_PROSE = " ".join([TEN_WORDS] * 15)  # one 150-word paragraph, over the 120-word full-read limit


def test_full_speech_reads_past_the_length_limits():
    reply = f"Opening line here.\n\n{LONG_PROSE}\n\nWant me to carry on?"
    assert full_speech(reply) == f"Opening line here. {LONG_PROSE} Want me to carry on?"


def test_full_speech_still_skips_code_blocks_and_tables():
    reply = "Before the code.\n\n```py\nprint(1)\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nAfter the table."
    assert full_speech(reply) == "Before the code. After the table."


def test_full_speech_reads_list_items_as_sentences():
    assert full_speech("Steps:\n\n- one\n- two\n\nDone") == "Steps: one. two. Done."


def test_full_speech_of_a_code_only_reply():
    assert full_speech("```py\nprint(1)\n```") == NOTHING_TO_SAY


def test_summary_is_the_last_speaker_paragraph():
    reply = "Screen text.\n\n🔊 An earlier summary.\n\nMore text.\n\n🔊 The fix is in. Shall I push it?"
    assert summary_speech(reply) == "The fix is in. Shall I push it?"


def test_summary_wrapped_over_two_lines_is_kept_whole():
    reply = "Body text.\n\n🔊 The fix is in and tested.\nShall I push it?\n\nTrailing note."
    assert summary_speech(reply) == "The fix is in and tested. Shall I push it?"


def test_summary_is_cleaned_like_other_speech():
    reply = "Body.\n\n🔊 I changed `src/auth/session.ts:42` and **all** tests pass"
    assert summary_speech(reply) == "I changed session.ts and all tests pass."


def test_summary_may_be_indented_or_use_the_emoji_variation_selector():
    assert summary_speech("Body.\n\n  🔊️ Done.") == "Done."


def test_summary_inside_a_code_block_is_ignored():
    assert summary_speech("Body.\n\n```text\n🔊 not this\n```\n") is None


def test_speaker_emoji_in_running_text_is_not_a_summary():
    assert summary_speech("I added a 🔊 icon to the toolbar.") is None


def test_summary_found_in_a_reply_with_windows_line_endings():
    assert summary_speech("Body.\r\n\r\n🔊 Short version.\r\n") == "Short version."


def test_no_summary_or_an_empty_one():
    assert summary_speech("Just a normal reply.") is None
    assert summary_speech("Body.\n\n🔊") is None
