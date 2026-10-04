"""Turn a Claude Code reply (Markdown) into the text that gets spoken."""
import re

REST_ON_SCREEN = "The rest is on screen."
NOTHING_TO_SAY = "Done. The details are on screen."
INLINE_CODE_MAX_WORDS = 3
INLINE_CODE_MAX_CHARS = 30

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
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?…])\s+")


def to_speech(markdown: str, full_read_max_words: int = 120, gist_max_words: int = 60) -> str:
    """Short replies are read in full; long ones give the opening paragraph, then REST_ON_SCREEN."""
    paragraphs = _paragraphs(markdown)
    if not paragraphs:
        return NOTHING_TO_SAY
    if sum(_word_count(p) for p in paragraphs) <= full_read_max_words:
        return " ".join(paragraphs)
    return f"{_trim(paragraphs[0], gist_max_words)} {REST_ON_SCREEN}"


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


def _paragraphs(markdown: str) -> list[str]:
    text = _FENCE.sub("\n", markdown.replace("\r\n", "\n"))
    text = _HTML_COMMENT.sub("", text)
    paragraphs: list[str] = []
    current: list[str] = []
    current_is_list = False

    for raw in text.split("\n"):
        if not raw.strip() or _HEADING.match(raw) or _RULE.match(raw) or _TABLE_ROW.match(raw):
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        line = _QUOTE.sub("", raw)
        is_list = bool(_LIST_ITEM.match(line))
        if is_list:
            line = _CHECKBOX.sub("", _LIST_ITEM.sub("", line, count=1))
        if current and is_list != current_is_list:
            paragraphs.append(" ".join(current))
            current = []
        line = _clean_inline(line)
        if not line:
            continue
        if not current:
            current_is_list = is_list
        current.append(_end_sentence(line) if is_list else line)

    if current:
        paragraphs.append(" ".join(current))
    return [_end_sentence(p) for p in paragraphs]


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
