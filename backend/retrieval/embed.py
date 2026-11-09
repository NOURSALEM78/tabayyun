"""Compute BGE-M3 embeddings for chunks and store them in PostgreSQL (pgvector).

Run with ``python -m backend.retrieval.embed``. Only chunks without an embedding
are encoded, so the command is cheap to re-run: after a reseed, chunks whose text
changed have their embedding cleared (see ``backend/db/seed.py``) and are encoded
again. ``--all`` re-encodes every chunk, e.g. after changing the model.
"""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Iterator, Sequence
from typing import Protocol

from sqlalchemy import Connection, select, update

from backend.db.config import EMBEDDING_DIMENSION
from backend.db.database import engine
from backend.db.models import Chunk
from backend.retrieval.constants import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MAX_TOKENS,
    EMBEDDING_MODEL_NAME,
)

logger = logging.getLogger(__name__)
Vector = list[float]


class Encoder(Protocol):
    """Anything that turns a batch of texts into normalised vectors."""

    def encode(self, texts: Sequence[str]) -> list[Vector]:
        """Return one vector per text."""
        ...


class EmbeddingError(ValueError):
    """Raised when the model returns vectors of the wrong size or count."""


class SentenceTransformerEncoder:
    """BGE-M3 through sentence-transformers, with L2-normalised output for cosine search."""

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME) -> None:
        from sentence_transformers import (
            SentenceTransformer,  # heavy import, load on demand
        )

        self._model = SentenceTransformer(model_name)
        self._model.max_seq_length = EMBEDDING_MAX_TOKENS

    def encode(self, texts: Sequence[str]) -> list[Vector]:
        """Encode texts as normalised float vectors."""
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]


def batched(items: Sequence[tuple[str, str]], size: int) -> Iterator[Sequence[tuple[str, str]]]:
    """Yield consecutive slices of at most ``size`` items."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


def encode_batch(encoder: Encoder, batch: Sequence[tuple[str, str]]) -> list[tuple[str, Vector]]:
    """Encode one batch of (chunk_id, text) and check every vector's size."""
    vectors = encoder.encode([text for _, text in batch])
    if len(vectors) != len(batch):
        raise EmbeddingError(f"Expected {len(batch)} vectors, received {len(vectors)}")
    for (chunk_id, _), vector in zip(batch, vectors, strict=True):
        if len(vector) != EMBEDDING_DIMENSION:
            raise EmbeddingError(
                f"{chunk_id}: expected {EMBEDDING_DIMENSION} dimensions, received {len(vector)}"
            )
    return [(chunk_id, vector) for (chunk_id, _), vector in zip(batch, vectors, strict=True)]


def pending_chunks(connection: Connection, recompute_all: bool = False) -> list[tuple[str, str]]:
    """Return (chunk_id, text) for chunks that need an embedding, in a stable order."""
    query = select(Chunk.chunk_id, Chunk.text).order_by(Chunk.chunk_id)
    if not recompute_all:
        query = query.where(Chunk.embedding.is_(None))
    return [(row.chunk_id, row.text) for row in connection.execute(query)]


def embed_chunks(
    encoder: Encoder,
    recompute_all: bool = False,
    batch_size: int = EMBEDDING_BATCH_SIZE,
) -> int:
    """Encode pending chunks batch by batch, committing after each batch; return the count."""
    with engine.connect() as connection:
        pending = pending_chunks(connection, recompute_all)
    logger.info("Chunks to embed: %d", len(pending))
    done = 0
    started = time.monotonic()
    for batch in batched(pending, batch_size):
        rows = encode_batch(encoder, batch)
        with engine.begin() as connection:
            for chunk_id, vector in rows:
                connection.execute(
                    update(Chunk).where(Chunk.chunk_id == chunk_id).values(embedding=vector)
                )
        done += len(rows)
        logger.info("Embedded %d/%d chunks (%.0fs)", done, len(pending), time.monotonic() - started)
    return done


def main() -> None:
    """Embed every chunk that has no embedding yet (or all chunks with --all)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Compute BGE-M3 embeddings for chunks.")
    parser.add_argument("--all", action="store_true", help="re-encode every chunk")
    arguments = parser.parse_args()
    logger.info("Loading %s (the first run downloads about 2 GB)", EMBEDDING_MODEL_NAME)
    count = embed_chunks(SentenceTransformerEncoder(), recompute_all=arguments.all)
    logger.info("Done: %d chunks embedded", count)


if __name__ == "__main__":
    main()
