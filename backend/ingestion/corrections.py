"""Apply reviewed OCR text corrections from data/seed/text_corrections.json.

Each correction belongs to one article (``doc`` + ``article``) and replaces one
exact text occurrence, so the same OCR mistake can be fixed differently in
different articles. A correction whose text is not found (or found more than
once) is reported and skipped, so corrections never change text silently.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from pathlib import Path

from backend.ingestion.constants import SEED_CORRECTIONS_FILE, SEED_DATA_DIR
from backend.ingestion.split import ArticleRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TextCorrection:
    """One reviewed replacement inside one article."""

    doc: str
    article: int
    find: str
    replace: str


def load_text_corrections(
    path: Path = SEED_DATA_DIR / SEED_CORRECTIONS_FILE,
) -> list[TextCorrection]:
    """Read corrections from JSON; a missing file means no corrections."""
    if not path.is_file():
        logger.info("No text corrections file at %s", path)
        return []
    with path.open(encoding="utf-8") as handle:
        entries = json.load(handle)["corrections"]
    return [
        TextCorrection(str(entry["doc"]), int(entry["article"]), entry["find"], entry["replace"])
        for entry in entries
    ]


def _apply_to_text(text: str, correction: TextCorrection) -> str | None:
    """Return corrected text, or None when the find text is missing or ambiguous."""
    count = text.count(correction.find)
    if count != 1:
        logger.warning(
            "Correction skipped for %s article %d (%s occurrence(s) of %r)",
            correction.doc,
            correction.article,
            count,
            correction.find,
        )
        return None
    return text.replace(correction.find, correction.replace)


def apply_text_corrections(
    articles: tuple[ArticleRecord, ...], corrections: list[TextCorrection] | None = None
) -> tuple[ArticleRecord, ...]:
    """Apply corrections in file order to the matching articles."""
    corrections = load_text_corrections() if corrections is None else corrections
    by_key = {(article.document_code, article.article_no): article for article in articles}
    applied = 0
    for correction in corrections:
        key = (correction.doc, correction.article)
        article = by_key.get(key)
        if article is None:
            logger.warning("Correction refers to a missing article: %s %d", *key)
            continue
        corrected = _apply_to_text(article.text, correction)
        if corrected is not None:
            by_key[key] = replace(article, text=corrected)
            applied += 1
    logger.info("Applied %d of %d text corrections", applied, len(corrections))
    return tuple(by_key[(article.document_code, article.article_no)] for article in articles)
