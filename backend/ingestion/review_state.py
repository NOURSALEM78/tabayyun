"""Track which articles the team has reviewed against the scanned PDFs.

An article counts as reviewed when it has at least one entry in
``text_corrections.json`` or is listed in ``reviewed_articles.json`` (articles
the team checked and marked clean, or checked and corrected).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path

from backend.ingestion.constants import SEED_DATA_DIR, SEED_REVIEWED_FILE
from backend.ingestion.corrections import TextCorrection

logger = logging.getLogger(__name__)

ArticleKey = tuple[str, int]

REVIEWED_NOTE = (
    "Articles checked word by word against the scanned PDFs. Articles with an entry in "
    "text_corrections.json are also treated as reviewed. Updated by review_import.py."
)


def load_reviewed_articles(path: Path = SEED_DATA_DIR / SEED_REVIEWED_FILE) -> set[ArticleKey]:
    """Read the reviewed list as (document code, article number) pairs."""
    if not path.is_file():
        logger.info("No reviewed-articles file at %s", path)
        return set()
    with path.open(encoding="utf-8") as handle:
        by_document: dict[str, list[int]] = json.load(handle)["reviewed"]
    return {(code, int(number)) for code, numbers in by_document.items() for number in numbers}


def save_reviewed_articles(
    keys: Iterable[ArticleKey], path: Path = SEED_DATA_DIR / SEED_REVIEWED_FILE
) -> None:
    """Write the reviewed list grouped by document, sorted for readable diffs."""
    by_document: dict[str, list[int]] = {}
    for code, number in sorted(set(keys)):
        by_document.setdefault(code, []).append(number)
    # One line per document keeps the file short and its git diffs readable.
    lines = [f'    "{code}": {json.dumps(numbers)}' for code, numbers in by_document.items()]
    body = ",\n".join(lines)
    note = json.dumps(REVIEWED_NOTE, ensure_ascii=False)
    path.write_text(
        f'{{\n  "_note": {note},\n  "reviewed": {{\n{body}\n  }}\n}}\n', encoding="utf-8"
    )
    logger.info("Saved %d reviewed articles to %s", sum(map(len, by_document.values())), path)


def reviewed_keys(
    reviewed: set[ArticleKey], corrections: Iterable[TextCorrection]
) -> set[ArticleKey]:
    """Combine the explicit reviewed list with every article that has a correction."""
    return reviewed | {(correction.doc, correction.article) for correction in corrections}
