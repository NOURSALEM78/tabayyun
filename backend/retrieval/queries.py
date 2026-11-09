"""Database queries for retrieval (pgvector search, visibility, overrides)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Connection, and_, exists, not_, select

from backend.db.models import (
    Article,
    Chunk,
    Document,
    DocumentAccess,
    DocumentRelation,
    Employee,
    Issuer,
    Role,
)
from backend.retrieval.constants import ACTIVE_DOCUMENT_STATUSES, OVERRIDING_RELATIONS
from backend.retrieval.types import Candidate, Override, Requester


class UnknownEmployeeError(LookupError):
    """Raised when the requester is not an active employee."""


def load_requester(connection: Connection, employee_id: str) -> Requester:
    """Return the employee's role and access level."""
    row = connection.execute(
        select(Employee.employee_id, Role.role_id, Role.access_level)
        .join(Role, Role.role_id == Employee.role_id)
        .where(Employee.employee_id == employee_id, Employee.is_active.is_(True))
    ).first()
    if row is None:
        raise UnknownEmployeeError(f"No active employee {employee_id}")
    return Requester(row.employee_id, row.role_id, row.access_level)


def visible_document_ids(connection: Connection, requester: Requester) -> set[int]:
    """Documents at or below the requester's level, and on the access list when one exists."""
    has_list = exists().where(DocumentAccess.doc_id == Document.doc_id)
    listed = exists().where(
        DocumentAccess.doc_id == Document.doc_id, DocumentAccess.role_id == requester.role_id
    )
    query = select(Document.doc_id).where(
        Document.classification_level <= requester.access_level,
        (not_(has_list)) | listed,
    )
    return set(connection.scalars(query))


def _candidate_query():
    """Chunks joined with their article and document, limited to rules in force."""
    return (
        select(
            Chunk.chunk_id,
            Chunk.text,
            Chunk.doc_id,
            Document.title.label("doc_title"),
            Chunk.article_id,
            Article.article_no,
            Article.article_label,
            Chunk.clause_no,
        )
        .join(Article, Article.article_id == Chunk.article_id)
        .join(Document, Document.doc_id == Chunk.doc_id)
        .where(
            Chunk.is_current.is_(True),
            Document.status.in_(ACTIVE_DOCUMENT_STATUSES),
            Article.status.in_(ACTIVE_DOCUMENT_STATUSES),
        )
    )


def _to_candidate(row) -> Candidate:
    return Candidate(
        row.chunk_id,
        row.text,
        row.doc_id,
        row.doc_title,
        row.article_id,
        row.article_no,
        row.article_label,
        row.clause_no,
    )


def vector_search(
    connection: Connection, embedding: Sequence[float], doc_ids: set[int], limit: int
) -> list[Candidate]:
    """Nearest chunks by cosine distance among the given documents."""
    query = (
        _candidate_query()
        .where(Chunk.embedding.is_not(None), Chunk.doc_id.in_(doc_ids))
        .order_by(Chunk.embedding.cosine_distance(list(embedding)), Chunk.chunk_id)
        .limit(limit)
    )
    return [_to_candidate(row) for row in connection.execute(query)]


def candidates_by_id(connection: Connection, chunk_ids: Sequence[str]) -> list[Candidate]:
    """Load candidates for the given chunk ids, keeping the given order."""
    rows = {
        row.chunk_id: _to_candidate(row)
        for row in connection.execute(_candidate_query().where(Chunk.chunk_id.in_(chunk_ids)))
    }
    return [rows[chunk_id] for chunk_id in chunk_ids if chunk_id in rows]


def searchable_chunk_ids(connection: Connection, doc_ids: set[int]) -> set[str]:
    """Chunk ids of rules in force within the given documents."""
    query = _candidate_query().where(Chunk.doc_id.in_(doc_ids))
    return {row.chunk_id for row in connection.execute(query)}


def keyword_corpus(connection: Connection) -> list[tuple[str, str]]:
    """(chunk_id, normalised text) for every current chunk, for the BM25 index."""
    query = select(Chunk.chunk_id, Chunk.text_normalized).where(Chunk.is_current.is_(True))
    return [(row.chunk_id, row.text_normalized) for row in connection.execute(query)]


def load_overrides(connection: Connection) -> list[Override]:
    """Relations in force from active documents that change other documents or articles."""
    source = Document.__table__.alias("source")
    query = (
        select(
            DocumentRelation.source_doc_id,
            source.c.title,
            DocumentRelation.target_doc_id,
            DocumentRelation.target_article_id,
            DocumentRelation.relation_type,
            Issuer.name,
            Issuer.referral_text,
            exists().where(Article.doc_id == DocumentRelation.source_doc_id).label("held"),
        )
        .join(source, source.c.doc_id == DocumentRelation.source_doc_id)
        .join(Issuer, Issuer.issuer_id == source.c.issuer_id)
        .where(
            and_(
                DocumentRelation.relation_type.in_(OVERRIDING_RELATIONS),
                source.c.status.in_(ACTIVE_DOCUMENT_STATUSES),
            )
        )
    )
    return [Override(*row) for row in connection.execute(query)]
