"""Lists for the interface: the employee's documents and access requests."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, exists, select
from sqlalchemy.orm import aliased

from backend.db.models import (
    AccessRequest,
    Action,
    Article,
    Document,
    DocumentRelation,
    Issuer,
    Resource,
    Role,
)
from backend.retrieval.constants import ACTIVE_DOCUMENT_STATUSES
from backend.retrieval.queries import load_requester, visible_document_ids
from backend.services.access import DECISION_LABELS, STATUS_PENDING
from backend.services.constants import CLASSIFICATION_NAMES, TOP_APPROVER_NAME

DOC_TYPE_LABELS = {
    "law": "نظام",
    "regulation": "لائحة",
    "circular": "تعميم",
    "decision": "قرار",
    "procedure_guide": "دليل إجراءات",
}
STATUS_LABELS = {"active": "ساري", "amended": "ساري (معدّل)"}


def documents_for(engine: Engine, employee_id: str) -> list[dict[str, Any]]:
    """Documents in force the employee may see that hold article text.

    Documents recorded only as amendments (e.g. «تعديلات المادة (n)», whose text the
    system does not hold) are not listed; their target shows ``has_amendments``.
    """
    with engine.connect() as connection:
        visible = visible_document_ids(connection, load_requester(connection, employee_id))
        # Articles marked as amended by a text the system does not hold (see README,
        # «Amended law articles»); public whole-document amendments are already in the text.
        amended = exists().where(
            DocumentRelation.target_doc_id == Document.doc_id,
            DocumentRelation.relation_type == "amends",
            DocumentRelation.target_article_id.is_not(None),
        )
        rows = connection.execute(
            select(
                Document.doc_id,
                Document.title,
                Document.doc_type,
                Document.status,
                Document.classification_level,
                Issuer.name.label("issuer"),
                amended.label("has_amendments"),
            )
            .join(Issuer, Issuer.issuer_id == Document.issuer_id)
            .where(
                Document.doc_id.in_(visible),
                Document.status.in_(ACTIVE_DOCUMENT_STATUSES),
                exists().where(Article.doc_id == Document.doc_id),
            )
            .order_by(Document.doc_id)
        )
        return [
            {
                "doc_id": row.doc_id,
                "title": row.title,
                "doc_type": DOC_TYPE_LABELS.get(row.doc_type, row.doc_type),
                "issuer": row.issuer,
                "classification": CLASSIFICATION_NAMES.get(row.classification_level, ""),
                "status": STATUS_LABELS.get(row.status, row.status),
                "has_amendments": bool(row.has_amendments),
            }
            for row in rows
        ]


def requests_for(engine: Engine, employee_id: str) -> list[dict[str, Any]]:
    """The employee's access requests, most recent first."""
    approver = aliased(Role)
    with engine.connect() as connection:
        rows = connection.execute(
            select(
                AccessRequest.request_id,
                AccessRequest.decision,
                AccessRequest.status,
                AccessRequest.created_at,
                Resource.name.label("resource_name"),
                Action.name.label("action_name"),
                approver.name_ar.label("approver_name"),
            )
            .join(Resource, Resource.resource_id == AccessRequest.resource_id)
            .join(Action, Action.action_id == AccessRequest.action_id)
            .outerjoin(approver, approver.role_id == AccessRequest.approver_role_id)
            .where(AccessRequest.employee_id == employee_id)
            .order_by(AccessRequest.request_id.desc())
        )
        return [
            {
                "request_id": row.request_id,
                "resource_name": row.resource_name,
                "action_name": row.action_name,
                "decision": row.decision,
                "decision_label": DECISION_LABELS.get(row.decision, row.decision),
                "status": row.status,
                "approver": (row.approver_name or TOP_APPROVER_NAME)
                if row.status == STATUS_PENDING
                else None,
                "created_at": row.created_at,
            }
            for row in rows
        ]
