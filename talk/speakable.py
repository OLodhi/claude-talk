"""Turn a Claude Code reply (Markdown) into the text that gets spoken."""
import re

REST_ON_SCREEN = "The rest is on screen."
DETAILS_ON_SCREEN = "The remainder of details are on screen."
NOTHING_TO_SAY = "Done. The details are on screen."
INLINE_CODE_MAX_WORDS = 3
INLINE_CODE_MAX_CHARS = 30

_CODE_SENTINEL = "\x00code"
_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]*\1[ \t]*$|\Z)", re.MULTILINE | re.DOTALL)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
_RULE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_TABLE_ROW = re.compile(r"^\s*\|")
_QUOTE = re.compile(r"^\s{0,3}(>\s?)+")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_CHECKBOX = re.compile(r"^\[[ xX]\]\s+")

_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_HTML_TAG = re.compile(r"</?[A-Za-z][^>\n]*>")
_URL = re.compile(r"(?:https?://|www\.)\S+")
_PATH = re.compile(
    r"(?:[A-Za-z]:)?[\\/]?(?:[\w.~-]+[\\/])+([\w.-]+\.[A-Za-z][A-Za-z0-9]*)(?::\d+(?:[:-]\d+)?)?"
)
_FILE_LINE = re.compile(r"\b([\w-]+\.[A-Za-z][A-Za-z0-9]*):\d+(?:[:-]\d+)?\b")
_BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_ITALIC_STAR = re.compile(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])")
_ITALIC_UNDERSCORE = re.compile(r"(?<![\w_])_(?=\S)(.+?)(?<=\S)_(?![\w_])")
_STRIKE = re.compile(r"~~(.+?)~~")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?…])\s+")
_SUMMARY_START = re.compile("^\\s*\U0001F50A️?")


def to_speech(
    markdown: str, full_read_max_words: int = 120, gist_max_words: int = 60, closing_max_words: int = 40
) -> str:
    """Short replies are read in full. Long ones give the opening paragraph (the gist), then either
    REST_ON_SCREEN, or, when the reply ends in a prose paragraph of its own, DETAILS_ON_SCREEN and
    the final sentences of that closing paragraph (at most closing_max_words)."""
    paragraphs = _paragraphs(markdown)
    if not paragraphs:
        return NOTHING_TO_SAY
    texts = [text for text, _ in paragraphs]
    if sum(_word_count(t) for t in texts) <= full_read_max_words:
        return " ".join(texts)
    gist, gist_end = _gist_paragraph(texts)
    spoken = _trim(gist, gist_max_words)
    closing = _closing(paragraphs, gist_end, markdown, closing_max_words)
    if closing:
        return f"{spoken} {DETAILS_ON_SCREEN} {closing}"
    return f"{spoken} {REST_ON_SCREEN}"


def full_speech(markdown: str) -> str:
    """Every speakable paragraph, in order, with no length limit (same cleanup as to_speech)."""
    texts = [text for text, _ in _paragraphs(markdown)]
    return " ".join(texts) if texts else NOTHING_TO_SAY


def summary_speech(markdown: str) -> str | None:
    """The spoken summary Claude writes in summary mode: the last paragraph starting with 🔊 (code blocks
    ignored), cleaned for speech. None when there is no such paragraph or it is empty."""
    text = _FENCE.sub("\n", markdown.replace("\r\n", "\n"))
    found: list[str] | None = None
    current: list[str] | None = None
    for line in text.split("\n"):
        if current is not None:
            if line.strip():
                current.append(line)
                continue
            found, current = current, None
        if _SUMMARY_START.match(line):
            current = [_SUMMARY_START.sub("", line, count=1)]
    if current is not None:
        found = current
    if found is None:
        return None
    spoken = _clean_inline(" ".join(found))
    return _end_sentence(spoken) if spoken else None


def _gist_paragraph(paragraphs: list[str]) -> tuple[str, int]:
    """The opening paragraph, skipping short label paragraphs and joining a "...:" intro to what follows.
    Also returns the index of the last paragraph used."""
    index = 0
    while (
        index + 1 < len(paragraphs)
        and _word_count(paragraphs[index]) < 4
        and not paragraphs[index].endswith(":")
    ):
        index += 1
    chosen = paragraphs[index]
    if chosen.endswith(":") and index + 1 < len(paragraphs):
        chosen = f"{chosen} {paragraphs[index + 1]}"
        index += 1
    return chosen, index


def _closing(paragraphs: list[tuple[str, bool]], gist_end: int, markdown: str, max_words: int) -> str:
    """The final sentences of the last paragraph, or "" when it should not be read."""
    last = len(paragraphs) - 1
    if last <= gist_end:
        return ""
    text, is_list = paragraphs[last]
    if is_list or text.endswith(":") or not _ends_in_prose(markdown):
        return ""
    return _trim_end(text, max_words)


def _ends_in_prose(markdown: str) -> bool:
    text = _FENCE.sub(f"\n{_CODE_SENTINEL}\n", markdown.replace("\r\n", "\n"))
    text = _HTML_COMMENT.sub("", text)
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return False
    last = lines[-1]
    if last.strip() == _CODE_SENTINEL:
        return False
    return not (
        _TABLE_ROW.match(last)
        or _HEADING.match(last)
        or _RULE.match(last)
        or _LIST_ITEM.match(_QUOTE.sub("", last))
    )


def _trim_end(text: str, max_words: int) -> str:
    kept: list[str] = []
    count = 0
    for sentence in reversed(split_sentences(text)):
        words = _word_count(sentence)
        if count + words > max_words:
            break
        kept.append(sentence)
        count += words
    return " ".join(reversed(kept))


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_BREAK.split(text.strip()) if s]


def speech_chunks(text: str, max_chars: int = 250) -> list[str]:
    """First sentence on its own (so speech starts fast), then sentences grouped up to max_chars."""
    sentences = split_sentences(text)
    if not sentences:
        return []
    chunks = [sentences[0]]
    current = ""
    for sentence in sentences[1:]:
        if current and len(current) + 1 + len(sentence) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def _paragraphs(markdown: str) -> list[tuple[str, bool]]:
    text = _FENCE.sub("\n", markdown.replace("\r\n", "\n"))
    text = _HTML_COMMENT.sub("", text)
    paragraphs: list[tuple[str, bool]] = []
    current: list[str] = []
    current_is_list = False

    for raw in text.split("\n"):
        if not raw.strip() or _HEADING.match(raw) or _RULE.match(raw) or _TABLE_ROW.match(raw):
            if current:
                paragraphs.append((" ".join(current), current_is_list))
                current = []
            continue
        line = _QUOTE.sub("", raw)
        is_list = bool(_LIST_ITEM.match(line))
        if is_list:
            line = _CHECKBOX.sub("", _LIST_ITEM.sub("", line, count=1))
        if current and is_list != current_is_list:
            paragraphs.append((" ".join(current), current_is_list))
            current = []
        line = _clean_inline(line)
        if not line:
            continue
        if not current:
            current_is_list = is_list
        current.append(_end_sentence(line) if is_list else line)

    if current:
        paragraphs.append((" ".join(current), current_is_list))
    return [(_end_sentence(p), is_list) for p, is_list in paragraphs]


def _clean_inline(line: str) -> str:
    line = _IMAGE.sub("", line)
    line = _LINK.sub(r"\1", line)
    line = _INLINE_CODE.sub(_speak_inline_code, line)
    line = _HTML_TAG.sub("", line)
    line = _URL.sub("", line)
    line = _PATH.sub(lambda m: m.group(1), line)
    line = _FILE_LINE.sub(r"\1", line)
    line = _BOLD.sub(r"\2", line)
    line = _ITALIC_STAR.sub(r"\1", line)
    line = _ITALIC_UNDERSCORE.sub(r"\1", line)
    line = _STRIKE.sub(r"\1", line)
    line = line.replace("→", " to ")
    line = _EMOJI.sub("", line)
    line = re.sub(r"\(\s*\)", "", line)
    line = re.sub(r"\s+", " ", line)
    line = re.sub(r"\s+([,.;:!?])", r"\1", line)
    return line.strip()


def _speak_inline_code(match: re.Match) -> str:
    code = match.group(1).strip()
    path = _PATH.fullmatch(code)
    if path:
        return path.group(1)
    code = _FILE_LINE.sub(r"\1", code)
    if len(code) <= INLINE_CODE_MAX_CHARS and len(code.split()) <= INLINE_CODE_MAX_WORDS:
        return code
    return ""


def _end_sentence(text: str) -> str:
    if text.rstrip("\"')]*")[-1:] in (".", "!", "?", ":", ";", "…"):
        return text
    return text + "."


def _word_count(text: str) -> int:
    return len(text.split())


def _trim(paragraph: str, max_words: int) -> str:
    kept: list[str] = []
    count = 0
    for sentence in split_sentences(paragraph):
        words = _word_count(sentence)
        if not kept and words > max_words:
            return " ".join(sentence.split()[:max_words]) + "…"
        if count + words > max_words:
            break
        kept.append(sentence)
        count += words
    return " ".join(kept)
