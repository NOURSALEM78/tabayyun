"""Tests for chunk embedding helpers and the reseed rule that clears stale embeddings."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from backend.db.config import EMBEDDING_DIMENSION
from backend.db.models import Chunk
from backend.db.seed import _embedding_if_text_unchanged
from backend.retrieval.embed import EmbeddingError, batched, encode_batch


class FakeEncoder:
    """Return a fixed-size vector per text; optionally the wrong size."""

    def __init__(self, dimension: int = EMBEDDING_DIMENSION) -> None:
        self.dimension = dimension
        self.calls: list[list[str]] = []

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(text))] * self.dimension for text in texts]


ITEMS = [(f"C{i}", "نص " * i) for i in range(5)]


def test_batched_keeps_order_and_size() -> None:
    assert [len(batch) for batch in batched(ITEMS, 2)] == [2, 2, 1]
    assert [item for batch in batched(ITEMS, 2) for item in batch] == ITEMS


def test_encode_batch_pairs_ids_with_vectors() -> None:
    encoder = FakeEncoder()
    rows = encode_batch(encoder, ITEMS[:2])

    assert [chunk_id for chunk_id, _ in rows] == ["C0", "C1"]
    assert all(len(vector) == EMBEDDING_DIMENSION for _, vector in rows)
    assert encoder.calls == [[text for _, text in ITEMS[:2]]]


def test_encode_batch_rejects_wrong_dimension() -> None:
    with pytest.raises(EmbeddingError, match="dimensions"):
        encode_batch(FakeEncoder(dimension=8), ITEMS[:1])


def test_reseed_clears_embedding_only_when_text_changes() -> None:
    table = Chunk.__table__
    statement = postgresql_insert(table).values(chunk_id="C1", text="نص")
    expression = _embedding_if_text_unchanged(table, statement)
    sql = str(expression.compile(dialect=postgresql.dialect()))

    assert "IS DISTINCT FROM" in sql
    assert "NULL" in sql and "chunks.embedding" in sql
