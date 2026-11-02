"""Recognise article-heading lines in OCR text without trusting the OCR digits."""

import re

from backend.ingestion.constants import (
    FORMATTING_CHARACTERS,
    HEADING_EXCLUDED_SUBSTRINGS,
    HEADING_EXCLUDED_WORDS,
    HEADING_MAX_WORDS,
    HEADING_STRIP_CHARACTERS,
    HEADING_TAIL_SENTENCE_END,
    HEADING_WORD_PATTERN,
)

_HEADING_WORD_RE = re.compile(HEADING_WORD_PATTERN)
_SENTENCE_END_RE = re.compile(HEADING_TAIL_SENTENCE_END)
_FORMATTING_TABLE = str.maketrans("", "", FORMATTING_CHARACTERS)


def _is_heading_word(word: str) -> bool:
    """Return whether a token is the word "المادة" not ending a sentence."""
    match = _HEADING_WORD_RE.match(word)
    return match is not None and not _SENTENCE_END_RE.search(match.group("tail"))


def _is_excluded(word: str) -> bool:
    """Return whether a token marks an in-text reference or amendment note."""
    bare = word.strip(HEADING_STRIP_CHARACTERS)
    return bare in HEADING_EXCLUDED_WORDS or any(
        part in word for part in HEADING_EXCLUDED_SUBSTRINGS
    )


def is_article_heading_line(line: str) -> bool:
    """Return whether an OCR line is an article heading such as "المادة (٤٠)".

    The line must be short, start or end with "المادة" (OCR may reverse
    right-to-left lines), and contain no words that indicate an in-text reference.
    """
    words = line.translate(_FORMATTING_TABLE).split()
    if not words or len(words) > HEADING_MAX_WORDS:
        return False
    if any(_is_excluded(word) for word in words):
        return False
    return _is_heading_word(words[0]) or _is_heading_word(words[-1])


def heading_number_token(line: str) -> str:
    """Return the heading text after removing the word "المادة", for review reports."""
    words = line.translate(_FORMATTING_TABLE).split()
    return " ".join(word for word in words if not _is_heading_word(word)).strip()
