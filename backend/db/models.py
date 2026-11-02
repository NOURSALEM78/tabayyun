"""SQLAlchemy models for Tabayyun's knowledge and access-control schema."""

from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.config import EMBEDDING_DIMENSION
from backend.db.database import Base

DOCUMENT_STATUS = Enum("active", "amended", "repealed", "suspended", name="document_status")
REVIEW_STATUS = Enum("draft", "approved", "excluded", name="review_status")


class Issuer(Base):
    """An organization that issues regulatory documents."""

    __tablename__ = "issuers"

    issuer_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    issuer_type: Mapped[str] = mapped_column(
        Enum("legislative", "executive", "internal", name="issuer_type")
    )
    referral_text: Mapped[str] = mapped_column(Text)


class Document(Base):
    """A source legal or procedural document."""

    __tablename__ = "documents"

    doc_id: Mapped[int] = mapped_column(primary_key=True)
    doc_type: Mapped[str] = mapped_column(
        Enum("law", "regulation", "circular", "decision", "procedure_guide", name="document_type")
    )
    title: Mapped[str] = mapped_column(Text)
    doc_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issuer_id: Mapped[int] = mapped_column(ForeignKey("issuers.issuer_id"))
    issue_date_hijri: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(DOCUMENT_STATUS)
    classification_level: Mapped[int] = mapped_column(SmallInteger)
    source_url: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Article(Base):
    """A versioned article belonging to a source document."""

    __tablename__ = "articles"
    __table_args__ = (UniqueConstraint("doc_id", "article_no", "version_no"),)

    article_id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.doc_id"))
    article_no: Mapped[int] = mapped_column(Integer)
    article_label: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(DOCUMENT_STATUS)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    classification_level: Mapped[int] = mapped_column(SmallInteger)
    rule_type: Mapped[str] = mapped_column(String(100))
    requires_approval: Mapped[bool] = mapped_column(Boolean)
    approver_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1, server_default=sql_text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Chunk(Base):
    """A searchable text segment sourced from an article."""

    __tablename__ = "chunks"
    __table_args__ = (
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_current_classification", "is_current", "classification_level"),
    )

    chunk_id: Mapped[str] = mapped_column(Text, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.article_id"))
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.doc_id"))
    clause_no: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    text_normalized: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION), nullable=True
    )
    classification_level: Mapped[int] = mapped_column(SmallInteger)
    is_current: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentRelation(Base):
    """A legal relationship between two documents or articles."""

    __tablename__ = "document_relations"

    relation_id: Mapped[int] = mapped_column(primary_key=True)
    source_doc_id: Mapped[int] = mapped_column(ForeignKey("documents.doc_id"))
    source_article_id: Mapped[int | None] = mapped_column(
        ForeignKey("articles.article_id"), nullable=True
    )
    target_doc_id: Mapped[int] = mapped_column(ForeignKey("documents.doc_id"))
    target_article_id: Mapped[int | None] = mapped_column(
        ForeignKey("articles.article_id"), nullable=True
    )
    relation_type: Mapped[str] = mapped_column(
        Enum("repeals", "amends", "replaces", "excepts", "interprets", name="relation_type")
    )
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text)


class DocumentAccess(Base):
    """An access scope associated with a document."""

    __tablename__ = "document_access"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.doc_id"))
    role_id: Mapped[str | None] = mapped_column(ForeignKey("roles.role_id"), nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)


class Procedure(Base):
    """A procedure derived from an official source."""

    __tablename__ = "procedures"

    procedure_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text))
    description: Mapped[str] = mapped_column(Text)
    responsible_department: Mapped[str] = mapped_column(Text)
    source_doc_id: Mapped[int] = mapped_column(ForeignKey("documents.doc_id"))
    source_article_id: Mapped[int] = mapped_column(ForeignKey("articles.article_id"))
    status: Mapped[str] = mapped_column(String(50))
    review_status: Mapped[str] = mapped_column(REVIEW_STATUS)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProcedureRequirement(Base):
    """A requirement in a procedure, with its source article."""

    __tablename__ = "procedure_requirements"

    requirement_id: Mapped[int] = mapped_column(primary_key=True)
    procedure_id: Mapped[int] = mapped_column(ForeignKey("procedures.procedure_id"))
    requirement_type: Mapped[str] = mapped_column(
        Enum("document", "condition", "statement", "deadline", "fee", name="requirement_type")
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    is_mandatory: Mapped[bool] = mapped_column(Boolean)
    source_article_id: Mapped[int] = mapped_column(ForeignKey("articles.article_id"))
    order_no: Mapped[int] = mapped_column(Integer)


class Role(Base):
    """A role used for employee and decision-rule authorization."""

    __tablename__ = "roles"

    role_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name_ar: Mapped[str] = mapped_column(Text)
    name_en: Mapped[str] = mapped_column(Text)
    access_level: Mapped[int] = mapped_column(SmallInteger)
    can_approve: Mapped[bool] = mapped_column(Boolean)


class Employee(Base):
    """An employee who can submit queries and access requests."""

    __tablename__ = "employees"

    employee_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.role_id"))
    department: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean)


class Action(Base):
    """An action that may be authorized for a resource."""

    __tablename__ = "actions"

    action_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    definition: Mapped[str] = mapped_column(Text)
    sensitivity: Mapped[str] = mapped_column(String(100))
    output_button: Mapped[str] = mapped_column(Text)


class Resource(Base):
    """A protected organizational resource and its review metadata."""

    __tablename__ = "resources"

    resource_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    synonyms: Mapped[list[str]] = mapped_column(ARRAY(Text))
    resource_type: Mapped[str] = mapped_column(String(100))
    source_doc_id: Mapped[int] = mapped_column(ForeignKey("documents.doc_id"))
    source_article_id: Mapped[int] = mapped_column(ForeignKey("articles.article_id"))
    classification_level: Mapped[int] = mapped_column(SmallInteger)
    classification_basis: Mapped[str] = mapped_column(Text)
    classification_ref: Mapped[str] = mapped_column(Text)
    custodian: Mapped[str] = mapped_column(Text)
    custodian_ref: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(REVIEW_STATUS)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DecisionRule(Base):
    """A role-resource-action decision and its legal justification."""

    __tablename__ = "decision_rules"
    __table_args__ = (UniqueConstraint("role_id", "resource_id", "action_id"),)

    rule_id: Mapped[str] = mapped_column(Text, primary_key=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.role_id"))
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.resource_id"))
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.action_id"))
    decision: Mapped[str] = mapped_column(
        Enum("allowed", "denied", "requires_approval", name="decision_type")
    )
    approver_role_id: Mapped[str | None] = mapped_column(ForeignKey("roles.role_id"), nullable=True)
    justification_article_id: Mapped[int | None] = mapped_column(
        ForeignKey("articles.article_id"), nullable=True
    )
    source: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Case(Base):
    """A procedure eligibility case submitted by an employee."""

    __tablename__ = "cases"

    case_id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.employee_id"))
    input_type: Mapped[str] = mapped_column(String(100))
    input_text: Mapped[str] = mapped_column(Text)
    attachment_path: Mapped[str] = mapped_column(Text)
    matched_procedure_id: Mapped[int | None] = mapped_column(
        ForeignKey("procedures.procedure_id"), nullable=True
    )
    match_score: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CaseFinding(Base):
    """The evaluated state of one procedure requirement in a case."""

    __tablename__ = "case_findings"

    finding_id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.case_id"))
    requirement_id: Mapped[int] = mapped_column(ForeignKey("procedure_requirements.requirement_id"))
    status: Mapped[str] = mapped_column(
        Enum("present", "missing", "unclear", name="finding_status")
    )
    evidence_text: Mapped[str] = mapped_column(Text)
    source_article_id: Mapped[int] = mapped_column(ForeignKey("articles.article_id"))


class QueryLog(Base):
    """A user's question, retrieval trace, and response category."""

    __tablename__ = "query_log"

    query_id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.employee_id"))
    question: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String(100))
    retrieved_chunk_ids: Mapped[list[str]] = mapped_column(ARRAY(Text))
    cited_chunk_ids: Mapped[list[str]] = mapped_column(ARRAY(Text))
    response_type: Mapped[str] = mapped_column(
        Enum("answer", "referral", "insufficient", name="response_type")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccessRequest(Base):
    """A request for an employee to perform an action on a resource."""

    __tablename__ = "access_requests"
    __table_args__ = (Index("ix_access_requests_status_approver", "status", "approver_role_id"),)

    request_id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.employee_id"))
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.resource_id"))
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.action_id"))
    decision: Mapped[str] = mapped_column(String(50))
    rule_id: Mapped[str] = mapped_column(ForeignKey("decision_rules.rule_id"))
    approver_role_id: Mapped[str] = mapped_column(ForeignKey("roles.role_id"))
    status: Mapped[str] = mapped_column(
        Enum("pending", "approved", "rejected", "auto", name="request_status")
    )
    approved_by: Mapped[str | None] = mapped_column(
        ForeignKey("employees.employee_id"), nullable=True
    )
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approver_note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccessGrant(Base):
    """A granted employee permission arising from an access request."""

    __tablename__ = "access_grants"

    grant_id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("access_requests.request_id"))
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.employee_id"))
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.resource_id"))
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.action_id"))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    """An auditable user or system event."""

    __tablename__ = "audit_log"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.employee_id"))
    event_type: Mapped[str] = mapped_column(
        Enum("query", "decision", "approval", "resource_opened", name="audit_event_type")
    )
    ref_id: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB)


class IngestionLog(Base):
    """A record of one ingestion run and its document counts."""

    __tablename__ = "ingestion_log"

    run_id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(Text)
    docs_added: Mapped[int] = mapped_column(Integer)
    docs_updated: Mapped[int] = mapped_column(Integer)
    docs_superseded: Mapped[int] = mapped_column(Integer)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
