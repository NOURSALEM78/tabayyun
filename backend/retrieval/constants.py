"""Constants for embeddings and retrieval."""

from typing import Final

# BGE-M3: multilingual (Arabic included), 1024-dimensional dense vectors, up to 8192 tokens.
EMBEDDING_MODEL_NAME: Final[str] = "BAAI/bge-m3"
EMBEDDING_BATCH_SIZE: Final[int] = 16
# Chunks are clauses, so 512 tokens covers them and keeps CPU encoding fast.
EMBEDDING_MAX_TOKENS: Final[int] = 512
