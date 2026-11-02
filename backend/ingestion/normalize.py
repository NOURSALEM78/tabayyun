"""Normalize Arabic text for search without changing source article text."""

import re
import unicodedata

from backend.ingestion.constants import PUNCTUATION_PATTERN

PUNCTUATION_RE = re.compile(PUNCTUATION_PATTERN)
WHITESPACE_RE = re.compile(r"\s+")


def normalize_arabic(text: str) -> str:
    """Remove Arabic diacritics, normalize letter forms, and strip punctuation."""
    normalized = unicodedata.normalize("NFKC", text)
    characters = [
        character for character in normalized if unicodedata.category(character) not in {"Mn", "Me"}
    ]
    normalized = "".join(characters).translate(
        str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"})
    )
    normalized = PUNCTUATION_RE.sub(" ", normalized)
    return WHITESPACE_RE.sub(" ", normalized).strip()
