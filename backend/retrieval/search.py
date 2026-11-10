"""Hybrid retrieval with permission, in-force and secret-amendment rules.

Steps for one question:
1. Find which documents the requester may see (classification level and access list).
2. Search those documents by meaning (BGE-M3 + pgvector) and by keywords (BM25).
3. Fuse both rankings (reciprocal rank fusion).
4. Keep each article once (its best-ranked chunk) and return the whole article.
5. Drop articles changed by a document the requester may not see, and return a
   referral to the competent authority instead; mark articles amended by a text the
   system does not hold with a notice and the referral.

Try it with ``python -m backend.retrieval.search "السؤال" --employee E001``.
"""

from __future__ import annotations

import argparse
import logging

from sqlalchemy import Engine

from backend.db.database import engine as default_engine
from backend.retrieval.constants import (
    KEYWORD_CANDIDATES,
    RESULTS_LIMIT,
    VECTOR_CANDIDATES,
)
from backend.retrieval.embed import Encoder, SentenceTransformerEncoder
from backend.retrieval.keyword import KeywordIndex
from backend.retrieval.queries import (
    candidates_by_id,
    keyword_corpus,
    load_overrides,
    load_requester,
    searchable_chunk_ids,
    vector_search,
    visible_document_ids,
)
from backend.retrieval.rules import apply_overrides, fuse_rankings
from backend.retrieval.types import RetrievalResult

logger = logging.getLogger(__name__)


class Retriever:
    """Answers retrieval requests; keeps the model and keyword index loaded between calls."""

    def __init__(self, encoder: Encoder, engine: Engine = default_engine) -> None:
        self._encoder = encoder
        self._engine = engine
        self._keyword_index: KeywordIndex | None = None

    def _keywords(self) -> KeywordIndex:
        """Build the BM25 index on first use."""
        if self._keyword_index is None:
            with self._engine.connect() as connection:
                self._keyword_index = KeywordIndex(keyword_corpus(connection))
        return self._keyword_index

    def retrieve(
        self, question: str, employee_id: str, limit: int = RESULTS_LIMIT
    ) -> RetrievalResult:
        """Return the chunks this employee may read for the question, and any referrals."""
        query_vector = self._encoder.encode([question])[0]
        with self._engine.connect() as connection:
            requester = load_requester(connection, employee_id)
            doc_ids = visible_document_ids(connection, requester)
            by_meaning = vector_search(connection, query_vector, doc_ids, VECTOR_CANDIDATES)
            allowed = searchable_chunk_ids(connection, doc_ids)
            keyword_ids = self._keywords().search(question, allowed, KEYWORD_CANDIDATES)
            by_keyword = candidates_by_id(connection, keyword_ids)
            overrides = load_overrides(connection)
        fused = fuse_rankings([by_meaning, by_keyword])
        result = apply_overrides(fused, overrides, doc_ids, limit)
        logger.info(
            "%s asked %r: %d chunks, %d referrals",
            employee_id,
            question,
            len(result.chunks),
            len(result.referrals),
        )
        return result


def _print(result: RetrievalResult) -> None:
    """Show a result in the terminal."""
    for referral in result.referrals:
        print(f"[إحالة] {referral.referral_text}")
    for number, chunk in enumerate(result.chunks, start=1):
        print(f"\n{number}. {chunk.doc_title} - {chunk.article_label} (أقرب بند: {chunk.clause_no})")
        text = chunk.article_text or chunk.text
        notice = result.amended_notices.get(chunk.chunk_id)
        # An amended article's text may no longer be in force, so it is never shown.
        print(f"   {notice}" if notice else f"   {text}")
        for title in result.changed_by.get(chunk.chunk_id, []):
            print(f"   ⚠ عُدّل حكم هذه المادة بموجب: {title}")
    if not result.chunks and not result.referrals:
        print("لم يُعثر على نص مناسب.")


def main() -> None:
    """Run one search from the command line."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Search the regulations as an employee.")
    parser.add_argument("question")
    parser.add_argument("--employee", default="E001")
    parser.add_argument("--limit", type=int, default=RESULTS_LIMIT)
    arguments = parser.parse_args()
    retriever = Retriever(SentenceTransformerEncoder())
    _print(retriever.retrieve(arguments.question, arguments.employee, arguments.limit))


if __name__ == "__main__":
    main()
