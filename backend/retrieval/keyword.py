"""Keyword (BM25) search over normalised chunk text.

Complements vector search for exact terms: article numbers, document names and
legal phrases. The index is built from all current chunks once per process;
visibility is applied by the caller.
"""

from __future__ import annotations

from collections.abc import Sequence

from rank_bm25 import BM25Okapi

from backend.ingestion.normalize import normalize_arabic


def tokenize(text: str) -> list[str]:
    """Split normalised Arabic text into word tokens."""
    return normalize_arabic(text).split()


class KeywordIndex:
    """BM25 index over (chunk_id, normalised text) pairs."""

    def __init__(self, documents: Sequence[tuple[str, str]]) -> None:
        self._ids = [chunk_id for chunk_id, _ in documents]
        self._bm25 = BM25Okapi([text.split() for _, text in documents]) if documents else None

    def search(self, query: str, allowed: set[str], limit: int) -> list[str]:
        """Return up to ``limit`` allowed chunk ids with a positive score, best first."""
        tokens = tokenize(query)
        if self._bm25 is None or not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(
            (
                (score, chunk_id)
                for chunk_id, score in zip(self._ids, scores, strict=True)
                if score > 0 and chunk_id in allowed
            ),
            key=lambda pair: (-pair[0], pair[1]),
        )
        return [chunk_id for _, chunk_id in ranked[:limit]]
