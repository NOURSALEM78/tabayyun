"""Generate the role x resource x action decision matrix from explicit rules.

General rule (SDAIA need-to-know and least privilege):
- classification above the role level by 2 or more -> denied
- above by 1 -> requires approval from the role's superior
- within the role level: viewing is allowed; downloading and sharing are allowed
  only for public resources; editing is allowed only for roles that can approve.
Sector rules from the Civil Status Law then apply to resources that carry them:
- no_transfer (Art. 11): sharing is denied
- committee_edit (Art. 15): editing needs the sub-committee (allowed for its members)
- official_copy (Art. 23): downloading needs approval after checking the interest
A sector rule never turns a "denied" decision into a softer one.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from backend.services.constants import (
    ACTION_DOWNLOAD,
    ACTION_EDIT,
    ACTION_SHARE,
    ACTION_VIEW,
    CLASSIFICATION_NAMES,
    COMMITTEE_ROLE_ID,
    DECISION_ALLOWED,
    DECISION_DENIED,
    DECISION_REQUIRES_APPROVAL,
    DEFAULT_APPROVER_ROLE_ID,
    DENY_LEVEL_GAP,
    PUBLIC_LEVEL,
    RULE_COMMITTEE_EDIT,
    RULE_NO_TRANSFER,
    RULE_OFFICIAL_COPY,
    SECTOR_RULE_ARTICLES,
    SOURCE_GENERAL,
    SOURCE_SECTOR,
    TOP_APPROVER_NAME,
)


@dataclass(frozen=True, slots=True)
class RoleSpec:
    """The parts of a role the decision rules need."""

    role_id: str
    name: str
    access_level: int
    can_approve: bool
    superior: str | None


@dataclass(frozen=True, slots=True)
class ResourceSpec:
    """The parts of a resource the decision rules need."""

    resource_id: str
    name: str
    classification_level: int
    sector_rules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Decision:
    """One decision with its approver, legal basis and explanation."""

    decision: str
    approver_role_id: str | None
    sector_article: int | None
    source: str
    explanation: str


def _approver_name(approver_id: str | None, role_names: dict[str, str]) -> str:
    """Return the approver's display name; no role means the General Directorate."""
    return role_names.get(approver_id, TOP_APPROVER_NAME) if approver_id else TOP_APPROVER_NAME


def general_decision(
    role: RoleSpec, resource: ResourceSpec, action_id: str, action_name: str, names: dict[str, str]
) -> Decision:
    """Apply the classification-based rule to one role, resource and action."""
    gap = resource.classification_level - role.access_level
    level = CLASSIFICATION_NAMES[resource.classification_level]
    role_level = CLASSIFICATION_NAMES[role.access_level]
    if gap >= DENY_LEVEL_GAP:
        return Decision(
            DECISION_DENIED,
            None,
            None,
            SOURCE_GENERAL,
            f"تصنيف المورد («{level}») أعلى من مستوى صلاحية الدور («{role_level}») "
            "بدرجتين أو أكثر؛ لذا يُرفض الطلب.",
        )
    approver = role.superior
    if gap == 1:
        return Decision(
            DECISION_REQUIRES_APPROVAL,
            approver,
            None,
            SOURCE_GENERAL,
            f"تصنيف المورد («{level}») أعلى من مستوى صلاحية الدور («{role_level}») "
            f"بدرجة واحدة؛ لذا يُحال الطلب إلى {_approver_name(approver, names)} للموافقة.",
        )
    allowed = Decision(
        DECISION_ALLOWED,
        None,
        None,
        SOURCE_GENERAL,
        f"المورد ضمن مستوى صلاحية الدور، وإجراء «{action_name}» مسموح ضمن هذا المستوى.",
    )
    if action_id == ACTION_VIEW:
        return allowed
    if action_id in (ACTION_DOWNLOAD, ACTION_SHARE):
        if resource.classification_level == PUBLIC_LEVEL:
            return allowed
        return Decision(
            DECISION_REQUIRES_APPROVAL,
            approver,
            None,
            SOURCE_GENERAL,
            f"المورد ضمن مستوى صلاحية الدور، غير أن إجراء «{action_name}» على مورد غير عام "
            f"يتطلب موافقة {_approver_name(approver, names)}.",
        )
    if action_id == ACTION_EDIT and role.can_approve:
        return allowed
    edit_approver = approver or DEFAULT_APPROVER_ROLE_ID
    return Decision(
        DECISION_REQUIRES_APPROVAL,
        edit_approver,
        None,
        SOURCE_GENERAL,
        "إجراء «تعديل» مقصور على الأدوار التي تملك صلاحية الموافقة؛ لذا يتطلب موافقة "
        f"{_approver_name(edit_approver, names)}.",
    )


def _sector_decision(
    role: RoleSpec, resource: ResourceSpec, action_id: str, names: dict[str, str]
) -> Decision | None:
    """Return the Civil Status Law decision for this action, if a sector rule applies."""
    rules = set(resource.sector_rules)
    if action_id == ACTION_SHARE and RULE_NO_TRANSFER in rules:
        article = SECTOR_RULE_ARTICLES[RULE_NO_TRANSFER]
        return Decision(
            DECISION_DENIED,
            None,
            article,
            SOURCE_SECTOR.format(article=article),
            "تنص المادة الحادية عشرة من نظام الأحوال المدنية على سرية بيانات السجلات المدنية "
            "وعدم جواز نقلها بأي حال من الأحوال؛ لذا يُرفض طلب المشاركة.",
        )
    if action_id == ACTION_EDIT and RULE_COMMITTEE_EDIT in rules:
        article = SECTOR_RULE_ARTICLES[RULE_COMMITTEE_EDIT]
        if role.role_id == COMMITTEE_ROLE_ID:
            return Decision(
                DECISION_ALLOWED,
                None,
                article,
                SOURCE_SECTOR.format(article=article),
                "التعديل في القيود الرئيسية من اختصاص اللجنة الفرعية (المادة الخامسة عشرة).",
            )
        return Decision(
            DECISION_REQUIRES_APPROVAL,
            COMMITTEE_ROLE_ID,
            article,
            SOURCE_SECTOR.format(article=article),
            "لا يجوز بعد تمام التسجيل التعديل في قيود الواقعات المدنية الرئيسية إلا بقرار من "
            "اللجنة الفرعية (المادة الخامسة عشرة)؛ لذا يُحال الطلب إلى عضو اللجنة الفرعية.",
        )
    if action_id == ACTION_DOWNLOAD and RULE_OFFICIAL_COPY in rules:
        article = SECTOR_RULE_ARTICLES[RULE_OFFICIAL_COPY]
        return Decision(
            DECISION_REQUIRES_APPROVAL,
            role.superior,
            article,
            SOURCE_SECTOR.format(article=article),
            "تقصر المادة الثالثة والعشرون استخراج الصور الرسمية على صاحب القيد وأقاربه والسلطات "
            "العامة المختصة وذوي المصلحة الثابتة؛ لذا يتطلب التحميل موافقة "
            f"{_approver_name(role.superior, names)} بعد التحقق من المصلحة.",
        )
    return None


def decide(
    role: RoleSpec, resource: ResourceSpec, action_id: str, action_name: str, names: dict[str, str]
) -> Decision:
    """Combine the general rule with sector rules; never soften a denial."""
    general = general_decision(role, resource, action_id, action_name, names)
    if general.decision == DECISION_DENIED:
        return general
    sector = _sector_decision(role, resource, action_id, names)
    return sector if sector is not None else general


def build_decision_rules(
    roles: Iterable[RoleSpec],
    resources: Iterable[ResourceSpec],
    actions: Iterable[tuple[str, str]],
    sector_article_ids: dict[int, int],
) -> list[dict[str, Any]]:
    """Return decision_rules rows for every role, resource and action."""
    role_list = list(roles)
    resource_list = list(resources)
    action_list = list(actions)
    names = {role.role_id: role.name for role in role_list}
    rows: list[dict[str, Any]] = []
    for role in role_list:
        for resource in resource_list:
            for action_id, action_name in action_list:
                result = decide(role, resource, action_id, action_name, names)
                rows.append(
                    {
                        "rule_id": f"DR{len(rows) + 1:05d}",
                        "role_id": role.role_id,
                        "resource_id": resource.resource_id,
                        "action_id": action_id,
                        "decision": result.decision,
                        "approver_role_id": result.approver_role_id,
                        "justification_article_id": (
                            sector_article_ids.get(result.sector_article)
                            if result.sector_article
                            else None
                        ),
                        "source": result.source,
                        "explanation": result.explanation,
                        "updated_at": None,
                    }
                )
    return rows
