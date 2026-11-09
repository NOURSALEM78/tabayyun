"""Constants for embeddings and retrieval."""

from typing import Final

# BGE-M3: multilingual (Arabic included), 1024-dimensional dense vectors, up to 8192 tokens.
EMBEDDING_MODEL_NAME: Final[str] = "BAAI/bge-m3"
EMBEDDING_BATCH_SIZE: Final[int] = 16
# Chunks are clauses, so 512 tokens covers them and keeps CPU encoding fast.
EMBEDDING_MAX_TOKENS: Final[int] = 512

# Hybrid search: candidates from each method, fused with reciprocal rank fusion (RRF).
VECTOR_CANDIDATES: Final[int] = 30
KEYWORD_CANDIDATES: Final[int] = 30
RRF_K: Final[int] = 60
RESULTS_LIMIT: Final[int] = 5

# Relations that make an article's public text no longer the rule in force.
OVERRIDING_RELATIONS: Final[tuple[str, ...]] = ("amends", "repeals", "replaces", "excepts")
ACTIVE_DOCUMENT_STATUSES: Final[tuple[str, ...]] = ("active", "amended")

# Shown with an article whose amendment text the system does not hold (the issuer's
# referral text follows it). The article itself must then be quoted, never summarised.
AMENDED_NOTICE: Final[str] = (
    "⚠ تنبيه: هذه المادة عليها تعديلات لدى الإدارة القانونية، ولا يتوفر للنظام نص التعديل."
)
