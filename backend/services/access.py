"""Path 2: decide an employee's access request from the decision matrix.

The decision is read from decision_rules (role x resource x action), never produced by
the language model. Every request is recorded in access_requests: decisions the matrix
settles (allowed, denied) as ``auto``, and those needing approval as ``pending``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import insert, select
from sqlalchemy.orm import Session, aliased

from backend.db.models import (
    AccessRequest,
    Action,
    Article,
    DecisionRule,
    Document,
    Employee,
    Resource,
    Role,
)
from backend.services.constants import (
    CLASSIFICATION_NAMES,
    DECISION_ALLOWED,
    DECISION_DENIED,
    DECISION_REQUIRES_APPROVAL,
    TOP_APPROVER_NAME,
)

DECISION_LABELS = {
    DECISION_ALLOWED: "مسموح",
    DECISION_DENIED: "مرفوض",
    DECISION_REQUIRES_APPROVAL: "يتطلب موافقة",
}
STATUS_AUTO = "auto"
STATUS_PENDING = "pending"


class AccessLookupError(LookupError):
    """Raised when the employee, resource, action or matching rule does not exist."""


@dataclass(frozen=True, slots=True)
class AccessDecision:
    """Everything shown to the employee for one access request."""

    request_id: int | None
    employee_id: str
    role_name: str
    resource_id: str
    resource_name: str
    classification: str
    action_id: str
    action_name: str
    decision: str
    decision_label: str
    status: str
    approver: str | None
    explanation: str
    legal_basis: str
    article: str | None
    next_step: str
    rule_id: str


def next_step(decision: str, output_button: str, approver: str | None, by_law: bool) -> str:
    """What the employee can do now (by_law: the decision rests on a specific article)."""
    if decision == DECISION_ALLOWED:
        return output_button
    if decision == DECISION_REQUIRES_APPROVAL:
        return f"أُحيل الطلب إلى {approver} للموافقة، وسيُتاح الإجراء بعد الموافقة."
    if by_law:
        return "هذا الإجراء غير جائز نظامًا على هذا المورد."
    return "لا يمكن تنفيذ هذا الإجراء بصلاحيات دورك الحالية."


def decide_access(
    session: Session, employee_id: str, resource_id: str, action_id: str, record: bool = True
) -> AccessDecision:
    """Look up the matrix decision for this employee's role and record the request."""
    employee = session.execute(
        select(Employee, Role)
        .join(Role, Role.role_id == Employee.role_id)
        .where(Employee.employee_id == employee_id, Employee.is_active.is_(True))
    ).first()
    if employee is None:
        raise AccessLookupError(f"No active employee {employee_id}")
    resource = session.get(Resource, resource_id)
    action = session.get(Action, action_id)
    if resource is None or action is None:
        raise AccessLookupError(f"Unknown resource {resource_id} or action {action_id}")
    approver_role = aliased(Role)
    row = session.execute(
        select(DecisionRule, approver_role.name_ar, Article.article_label, Document.title)
        .outerjoin(approver_role, approver_role.role_id == DecisionRule.approver_role_id)
        .outerjoin(Article, Article.article_id == DecisionRule.justification_article_id)
        .outerjoin(Document, Document.doc_id == Article.doc_id)
        .where(
            DecisionRule.role_id == employee.Role.role_id,
            DecisionRule.resource_id == resource_id,
            DecisionRule.action_id == action_id,
        )
    ).first()
    if row is None:
        raise AccessLookupError(f"No rule for {employee.Role.role_id}/{resource_id}/{action_id}")
    rule = row.DecisionRule
    approver = None
    if rule.decision == DECISION_REQUIRES_APPROVAL:
        approver = row.name_ar or TOP_APPROVER_NAME
    article = f"{row.title}، {row.article_label}" if row.article_label else None
    status = STATUS_PENDING if rule.decision == DECISION_REQUIRES_APPROVAL else STATUS_AUTO
    request_id = None
    if record:
        request_id = session.execute(
            insert(AccessRequest)
            .values(
                employee_id=employee_id,
                resource_id=resource_id,
                action_id=action_id,
                decision=rule.decision,
                rule_id=rule.rule_id,
                approver_role_id=rule.approver_role_id,
                status=status,
            )
            .returning(AccessRequest.request_id)
        ).scalar_one()
        session.commit()
    return AccessDecision(
        request_id=request_id,
        employee_id=employee_id,
        role_name=employee.Role.name_ar,
        resource_id=resource_id,
        resource_name=resource.name,
        classification=CLASSIFICATION_NAMES.get(resource.classification_level, ""),
        action_id=action_id,
        action_name=action.name,
        decision=rule.decision,
        decision_label=DECISION_LABELS[rule.decision],
        status=status,
        approver=approver,
        explanation=rule.explanation,
        legal_basis=rule.source,
        article=article,
        next_step=next_step(
            rule.decision, action.output_button, approver, rule.justification_article_id is not None
        ),
        rule_id=rule.rule_id,
    )

