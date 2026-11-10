"""Tests for the declared database schema and PostgreSQL-specific indexes."""

from backend.db.models import AccessRequest, Article, Base, Chunk, DecisionRule

EXPECTED_TABLES = {
    "issuers",
    "documents",
    "articles",
    "chunks",
    "document_relations",
    "document_access",
    "procedures",
    "procedure_requirements",
    "roles",
    "employees",
    "actions",
    "resources",
    "decision_rules",
    "cases",
    "case_findings",
    "query_log",
    "conversations",
    "messages",
    "access_requests",
    "access_grants",
    "audit_log",
    "ingestion_log",
}


def test_schema_has_exactly_the_requested_tables() -> None:
    """Ensure the ORM declares all 22 tables (20 requested plus chat history) and no extras."""
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_unique_constraints_match_the_schema() -> None:
    """Ensure article versions and role-resource-action rules are unique."""
    article_constraints = [
        {column.name for column in constraint.columns}
        for constraint in Article.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    ]
    rule_constraints = [
        {column.name for column in constraint.columns}
        for constraint in DecisionRule.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    ]

    assert {"doc_id", "article_no", "version_no"} in article_constraints
    assert {"role_id", "resource_id", "action_id"} in rule_constraints


def test_postgresql_indexes_are_declared() -> None:
    """Ensure vector search and pending-approval lookup indexes exist."""
    chunk_indexes = {index.name: index for index in Chunk.__table__.indexes}
    request_indexes = {index.name: index for index in AccessRequest.__table__.indexes}

    assert "ix_chunks_embedding_hnsw" in chunk_indexes
    assert (
        chunk_indexes["ix_chunks_embedding_hnsw"].dialect_options["postgresql"]["using"] == "hnsw"
    )
    assert "ix_chunks_current_classification" in chunk_indexes
    assert "ix_access_requests_status_approver" in request_indexes
