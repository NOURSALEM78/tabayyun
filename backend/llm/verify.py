"""Checks that a model's answer is grounded in the sources it cites.

The model's text is shown only when every check passes:

1. Each sentence cites at least one given source, e.g. [1].
2. Each number in a sentence (digits or Arabic number words such as «خمسة عشر»)
   appears in the sources that sentence cites (or in their citation labels).

Before the checks, a sentence without a citation that repeats a source word for word
gets that source's number (``attach_verbatim_citations``): text copied exactly from an
article is grounded by definition. These checks cannot prove that an answer is right, but they catch the common ways a
model invents a rule: a statement with no source, or a period, age or count that no
source contains. An answer that fails is not shown; the articles themselves are.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

_CITATION = re.compile(r"\[(\d+)\]")
_SENTENCE_END = re.compile(r"(?<=[.؟!:])\s+|\n+")
_DIACRITICS = re.compile(r"[ً-ْـ]")
_DIGITS = re.compile(r"\d+")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_PREFIXES = ("و", "ب", "ل", "ف")

# Normalised spellings (ة→ه, ى→ي, أإآ→ا) of Arabic number words.
_UNITS = {
    "واحد": 1, "واحده": 1,
    "اثنان": 2, "اثنين": 2, "اثنتان": 2, "اثنتين": 2,
    "ثلاث": 3, "ثلاثه": 3, "اربع": 4, "اربعه": 4, "خمس": 5, "خمسه": 5,
    "ست": 6, "سته": 6, "سبع": 7, "سبعه": 7, "ثمان": 8, "ثماني": 8, "ثمانيه": 8,
    "تسع": 9, "تسعه": 9,
}
# «أحد»/«اثنا» also mean "one of"/"any", so they count only before «عشر» (11, 12).
_COMPOUND_ONLY = {"احد": 1, "احدي": 1, "اثنا": 2, "اثني": 2, "اثنتا": 2}
_TEN = {"عشر", "عشره"}
_TENS = {
    "عشرون": 20, "عشرين": 20, "ثلاثون": 30, "ثلاثين": 30, "اربعون": 40, "اربعين": 40,
    "خمسون": 50, "خمسين": 50, "ستون": 60, "ستين": 60, "سبعون": 70, "سبعين": 70,
    "ثمانون": 80, "ثمانين": 80, "تسعون": 90, "تسعين": 90,
}
_LARGE = {"مائه": 100, "مئه": 100, "مائتان": 200, "مائتين": 200, "الف": 1000}


@dataclass(frozen=True, slots=True)
class Verdict:
    """Whether an answer may be shown, and why not."""

    ok: bool
    reason: str = ""


def normalise(text: str) -> str:
    """Remove diacritics and unify letter forms so number words compare reliably."""
    text = _DIACRITICS.sub("", text.translate(_ARABIC_DIGITS))
    for source, target in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي")):
        text = text.replace(source, target)
    return text


def _word_value(word: str) -> tuple[str, int] | None:
    """(kind, value) of a single number word, allowing a prefix and a final alif."""
    candidates = [word]
    if word[:1] in _PREFIXES and len(word) > 2:
        candidates.append(word[1:])
    for candidate in list(candidates):
        if candidate.endswith("ا") and len(candidate) > 3:
            candidates.append(candidate[:-1])
    for candidate in candidates:
        if candidate in _UNITS:
            return "unit", _UNITS[candidate]
        if candidate in _COMPOUND_ONLY:
            return "compound", _COMPOUND_ONLY[candidate]
        if candidate in _TEN:
            return "ten", 10
        if candidate in _TENS:
            return "tens", _TENS[candidate]
        if candidate in _LARGE:
            return "large", _LARGE[candidate]
    return None


def numbers_in(text: str) -> set[int]:
    """Every number written in digits or Arabic words, with compounds combined
    («خمسة عشر» → 15, «خمسة وعشرون» → 25)."""
    text = normalise(_CITATION.sub(" ", text))
    found = {int(digits) for digits in _DIGITS.findall(text)}
    words = re.findall(r"[ء-ي]+", text)
    index = 0
    while index < len(words):
        parsed = _word_value(words[index])
        if parsed is None:
            index += 1
            continue
        kind, value = parsed
        following = _word_value(words[index + 1]) if index + 1 < len(words) else None
        if kind == "compound":
            if following and following[0] == "ten":
                found.add(value + 10)
                index += 2
            else:
                index += 1
        elif kind == "unit" and following and following[0] == "ten":
            found.add(value + 10)
            index += 2
        elif kind == "unit" and following and following[0] == "tens":
            found.add(value + following[1])
            index += 2
        else:
            found.add(value)
            index += 1
    return found


def _sentences(text: str) -> list[str]:
    """Split an answer into sentences that carry content."""
    parts = (part.strip() for part in _SENTENCE_END.split(text))
    return [part for part in parts if re.search(r"[ء-ي]", part)]


def verify_answer(text: str, sources: Mapping[int, str]) -> Verdict:
    """Check an answer against the given sources ({number: citation + article text})."""
    sentences = _sentences(text)
    if not sentences:
        return Verdict(False, "empty answer")
    for sentence in sentences:
        cited = [int(number) for number in _CITATION.findall(sentence)]
        if not cited:
            return Verdict(False, f"sentence without a source: {sentence}")
        unknown = [number for number in cited if number not in sources]
        if unknown:
            return Verdict(False, f"cites a source that was not given: {unknown}")
        allowed: set[int] = set()
        for number in cited:
            allowed |= numbers_in(sources[number])
        missing = sorted(numbers_in(sentence) - allowed)
        if missing:
            return Verdict(False, f"numbers not in the cited sources {missing}: {sentence}")
    return Verdict(True)


# A sentence is treated as copied from a source only if it is at least this many words.
_MIN_VERBATIM_WORDS = 5
_PIECE = re.compile(r"[^.؟!\n]+[.؟!]*")


def _words(text: str) -> str:
    """Normalised words only, for comparing a sentence with a source text."""
    return " ".join(re.findall(r"[ء-ي0-9]+", normalise(text)))


def attach_verbatim_citations(text: str, sources: Mapping[int, str]) -> str:
    """Add [n] to each uncited sentence that repeats source n's text word for word."""
    source_words = {number: f" {_words(body)} " for number, body in sources.items()}

    def cite(match: re.Match[str]) -> str:
        piece = match.group(0)
        if _CITATION.search(piece):
            return piece
        words = _words(piece)
        if len(words.split()) < _MIN_VERBATIM_WORDS:
            return piece
        for number, body in source_words.items():
            if f" {words} " in body:
                core = piece.rstrip(".؟! ")
                return f"{core} [{number}]{piece[len(core):]}"
        return piece

    return _PIECE.sub(cite, text)
