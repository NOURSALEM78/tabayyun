"""Tests for the role x resource x action decision rules."""

from __future__ import annotations

import pytest

from backend.services.decision_matrix import (
    ResourceSpec,
    RoleSpec,
    build_decision_rules,
    decide,
)

NAMES = {
    "R1": "كاتب السجل",
    "R3": "رئيس مكتب الأحوال المدنية",
    "R4": "مدير الإدارة",
    "R5": "عضو اللجنة الفرعية",
}
REGISTRAR = RoleSpec("R1", "كاتب السجل", 3, False, "R3")
DIRECTOR = RoleSpec("R4", "مدير الإدارة", 4, True, None)
COMMITTEE = RoleSpec("R5", "عضو اللجنة الفرعية", 3, True, "R4")
ADMIN = RoleSpec("R7", "مسؤول النظام", 1, False, "R3")
CIVIL_RECORD = ResourceSpec(
    "RS1", "سجل المواليد", 3, ("no_transfer", "committee_edit", "official_copy")
)
CERTIFICATE = ResourceSpec("RS2", "شهادة الميلاد", 2, ())
FORM = ResourceSpec("RS3", "نموذج التبليغ", 1, ())


@pytest.mark.parametrize(
    ("role", "resource", "action", "decision", "approver", "article"),
    [
        (ADMIN, CIVIL_RECORD, "A1", "denied", None, None),  # gap 2 -> denied
        (ADMIN, CERTIFICATE, "A1", "requires_approval", "R3", None),  # gap 1 -> superior
        (REGISTRAR, CERTIFICATE, "A1", "allowed", None, None),
        (REGISTRAR, CERTIFICATE, "A2", "requires_approval", "R3", None),
        (REGISTRAR, FORM, "A2", "allowed", None, None),
        (REGISTRAR, CERTIFICATE, "A3", "requires_approval", "R3", None),
        (REGISTRAR, CIVIL_RECORD, "A4", "denied", None, 11),  # Art. 11: no transfer
        (DIRECTOR, CIVIL_RECORD, "A4", "denied", None, 11),
        (REGISTRAR, CIVIL_RECORD, "A3", "requires_approval", "R5", 15),  # Art. 15
        (COMMITTEE, CIVIL_RECORD, "A3", "allowed", None, 15),
        (REGISTRAR, CIVIL_RECORD, "A2", "requires_approval", "R3", 23),  # Art. 23
        (DIRECTOR, CERTIFICATE, "A2", "requires_approval", None, None),  # to the directorate
        (ADMIN, CIVIL_RECORD, "A3", "denied", None, None),  # sector rule never softens denial
    ],
)
def test_decisions(
    role: RoleSpec,
    resource: ResourceSpec,
    action: str,
    decision: str,
    approver: str | None,
    article: int | None,
) -> None:
    """Each documented rule produces the expected decision, approver and article."""
    result = decide(role, resource, action, "إجراء", NAMES)

    assert (result.decision, result.approver_role_id, result.sector_article) == (
        decision,
        approver,
        article,
    )
    assert result.explanation


def test_directorate_named_when_no_superior() -> None:
    """A request from the top role is explained as going to the General Directorate."""
    result = decide(DIRECTOR, CERTIFICATE, "A2", "تحميل", NAMES)

    assert "المديرية العامة للأحوال المدنية" in result.explanation


def test_build_rules_covers_every_combination_and_links_articles() -> None:
    """One unique rule per role, resource and action, with sector articles resolved."""
    rows = build_decision_rules(
        [REGISTRAR, COMMITTEE],
        [CIVIL_RECORD, FORM],
        [("A1", "اطلاع"), ("A4", "مشاركة")],
        {11: 111, 15: 115, 23: 123},
    )

    assert len(rows) == 2 * 2 * 2
    assert len({(r["role_id"], r["resource_id"], r["action_id"]) for r in rows}) == len(rows)
    share = next(r for r in rows if r["resource_id"] == "RS1" and r["action_id"] == "A4")
    assert share["justification_article_id"] == 111
