"""Load hand-reviewed reference data (issuers, documents, relations, procedures).

Facts that OCR cannot read reliably (decision numbers, dates, which document
repeals which) and data that needs human judgement (procedures) are kept in
JSON files under data/seed/, so they can be corrected without touching code.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.ingestion.constants import (
    DOCUMENT_SPECS,
    PROCEDURE_REVIEW_DRAFT,
    PUBLIC_CLASSIFICATION_LEVEL,
    SEED_DATA_DIR,
    SEED_DOCUMENTS_FILE,
    SEED_ISSUERS_FILE,
    SEED_PROCEDURES_FILE,
    SEED_REFERENCE_FILE,
    SEED_RELATIONS_FILE,
    SEED_RESOURCES_FILE,
)
from backend.services.constants import SECTOR_LAW_CODE, SECTOR_RULE_ARTICLES
from backend.services.decision_matrix import (
    ResourceSpec,
    RoleSpec,
    build_decision_rules,
)

logger = logging.getLogger(__name__)
Row = dict[str, Any]
ArticleKey = tuple[str, int]


class SeedDataError(ValueError):
    """Raised when a seed file refers to an unknown issuer, document, or article."""


@dataclass(frozen=True, slots=True)
class SeedRows:
    """Rows built from the seed files, ready for export."""

    issuers: tuple[Row, ...]
    documents: tuple[Row, ...]
    relations: tuple[Row, ...]
    procedures: tuple[Row, ...]
    requirements: tuple[Row, ...]
    roles: tuple[Row, ...] = ()
    actions: tuple[Row, ...] = ()
    employees: tuple[Row, ...] = ()
    resources: tuple[Row, ...] = ()
    decision_rules: tuple[Row, ...] = ()


def _load(path: Path, key: str) -> list[dict[str, Any]]:
    """Read one seed JSON file and return its list under ``key``."""
    if not path.is_file():
        raise FileNotFoundError(f"Seed file is missing: {path}")
    with path.open(encoding="utf-8") as handle:
        return list(json.load(handle)[key])


def _issuer_rows(entries: list[dict[str, Any]]) -> tuple[list[Row], dict[str, int]]:
    """Build issuer rows and a key -> issuer_id map."""
    rows: list[Row] = []
    ids: dict[str, int] = {}
    for issuer_id, entry in enumerate(entries, start=1):
        ids[entry["key"]] = issuer_id
        rows.append(
            {
                "issuer_id": issuer_id,
                "name": entry["name"],
                "issuer_type": entry["issuer_type"],
                "referral_text": entry["referral_text"],
            }
        )
    return rows, ids


def _document_rows(
    entries: list[dict[str, Any]],
    issuer_ids: dict[str, int],
    source_hashes: dict[str, str],
    timestamp: datetime,
) -> tuple[list[Row], dict[str, int]]:
    """Build document rows; source documents keep their DOCUMENT_SPECS doc_id."""
    specs = {spec.code: spec for spec in DOCUMENT_SPECS}
    next_id = max(spec.doc_id for spec in DOCUMENT_SPECS) + 1
    rows: list[Row] = []
    ids: dict[str, int] = {}
    for entry in entries:
        name = entry.get("code") or entry["key"]
        spec = specs.get(entry.get("code", ""))
        if entry.get("code") and spec is None:
            raise SeedDataError(f"Unknown source document code in seed: {name}")
        if entry["issuer"] not in issuer_ids:
            raise SeedDataError(f"Unknown issuer {entry['issuer']!r} for document {name}")
        doc_id = spec.doc_id if spec else next_id
        next_id += 0 if spec else 1
        ids[name] = doc_id
        rows.append(
            {
                "doc_id": doc_id,
                "doc_type": entry["doc_type"],
                "title": entry["title"],
                "doc_number": entry.get("doc_number") or "",
                "issuer_id": issuer_ids[entry["issuer"]],
                "issue_date_hijri": entry.get("issue_date_hijri") or "",
                "issue_date": None,
                "effective_from": None,
                "effective_to": None,
                "status": entry["status"],
                "classification_level": PUBLIC_CLASSIFICATION_LEVEL,
                "source_url": entry.get("evidence", ""),
                "file_path": f"data/raw/{spec.source_filename}" if spec else "",
                "content_hash": source_hashes.get(spec.source_filename, "") if spec else "",
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )
    missing = set(specs) - set(ids)
    if missing:
        raise SeedDataError(f"Seed documents.json lacks source documents: {sorted(missing)}")
    return sorted(rows, key=lambda row: row["doc_id"]), ids


def _article_id(ref: dict[str, Any] | None, article_ids: dict[ArticleKey, int]) -> int | None:
    """Resolve {"doc": code, "article": number} to an article_id."""
    if not ref:
        return None
    key = (ref["doc"], int(ref["article"]))
    if key not in article_ids:
        raise SeedDataError(f"Seed refers to an article that was not extracted: {key}")
    return article_ids[key]


def _relation_rows(
    entries: list[dict[str, Any]],
    doc_ids: dict[str, int],
    article_ids: dict[ArticleKey, int],
) -> list[Row]:
    """Build document_relations rows from relations.json."""
    rows: list[Row] = []
    for relation_id, entry in enumerate(entries, start=1):
        for side in ("source", "target"):
            if entry[side] not in doc_ids:
                raise SeedDataError(f"Unknown {side} document in relation: {entry[side]}")
        source_article = entry.get("source_article")
        target_article = entry.get("target_article")
        rows.append(
            {
                "relation_id": relation_id,
                "source_doc_id": doc_ids[entry["source"]],
                "source_article_id": _article_id(
                    {"doc": entry["source"], "article": source_article} if source_article else None,
                    article_ids,
                ),
                "target_doc_id": doc_ids[entry["target"]],
                "target_article_id": _article_id(
                    {"doc": entry["target"], "article": target_article} if target_article else None,
                    article_ids,
                ),
                "relation_type": entry["relation_type"],
                "effective_from": None,
                "notes": entry["notes"],
            }
        )
    return rows


def _procedure_rows(
    entries: list[dict[str, Any]],
    doc_ids: dict[str, int],
    article_ids: dict[ArticleKey, int],
    timestamp: datetime,
) -> tuple[list[Row], list[Row]]:
    """Build procedure and procedure_requirement rows from procedures.json."""
    procedures: list[Row] = []
    requirements: list[Row] = []
    for procedure_id, entry in enumerate(entries, start=1):
        procedures.append(
            {
                "procedure_id": procedure_id,
                "name": entry["name"],
                "aliases": entry.get("aliases", []),
                "description": entry.get("description", ""),
                "responsible_department": entry.get("responsible_department", ""),
                "source_doc_id": doc_ids[entry["source"]["doc"]],
                "source_article_id": _article_id(entry["source"], article_ids),
                "status": PROCEDURE_REVIEW_DRAFT,
                "review_status": entry.get("review_status", PROCEDURE_REVIEW_DRAFT),
                "updated_at": timestamp,
            }
        )
        for order_no, requirement in enumerate(entry["requirements"], start=1):
            requirements.append(
                {
                    "requirement_id": len(requirements) + 1,
                    "procedure_id": procedure_id,
                    "requirement_type": requirement["type"],
                    "name": requirement["name"],
                    "description": requirement.get("description", requirement["name"]),
                    "is_mandatory": bool(requirement["mandatory"]),
                    "source_article_id": _article_id(requirement["source"], article_ids),
                    "order_no": order_no,
                }
            )
    return procedures, requirements


def _access_rows(
    seed_dir: Path,
    doc_ids: dict[str, int],
    article_ids: dict[ArticleKey, int],
    timestamp: datetime,
) -> tuple[list[Row], list[Row], list[Row], list[Row], list[Row]]:
    """Build roles, actions, employees and resources, then generate the decision matrix."""
    with (seed_dir / SEED_REFERENCE_FILE).open(encoding="utf-8") as handle:
        reference = json.load(handle)
    resource_entries = _load(seed_dir / SEED_RESOURCES_FILE, "resources")
    role_ids = {role["role_id"] for role in reference["roles"]}

    roles = [
        {key: role[key] for key in ("role_id", "name_ar", "name_en", "access_level", "can_approve")}
        for role in reference["roles"]
    ]
    actions = [
        {
            key: action[key]
            for key in ("action_id", "name", "definition", "sensitivity", "output_button")
        }
        for action in reference["actions"]
    ]
    employees = []
    for employee in reference["employees"]:
        if employee["role_id"] not in role_ids:
            raise SeedDataError(f"Unknown role {employee['role_id']} for {employee['employee_id']}")
        employees.append({**employee, "is_active": employee.get("is_active", True)})

    resources = [
        {
            "resource_id": entry["resource_id"],
            "name": entry["name"],
            "synonyms": entry.get("synonyms", []),
            "resource_type": entry["resource_type"],
            "source_doc_id": doc_ids[entry["source"]["doc"]],
            "source_article_id": _article_id(entry["source"], article_ids),
            "classification_level": entry["classification_level"],
            "classification_basis": entry["classification_basis"],
            "classification_ref": entry["classification_ref"],
            "custodian": entry["custodian"],
            "custodian_ref": entry["custodian_ref"],
            "review_status": entry.get("review_status", PROCEDURE_REVIEW_DRAFT),
            "updated_at": timestamp,
        }
        for entry in resource_entries
    ]
    rules = build_decision_rules(
        [
            RoleSpec(r["role_id"], r["name_ar"], r["access_level"], r["can_approve"], r["superior"])
            for r in reference["roles"]
        ],
        [
            ResourceSpec(
                e["resource_id"], e["name"], e["classification_level"], tuple(e["sector_rules"])
            )
            for e in resource_entries
        ],
        [(action["action_id"], action["name"]) for action in reference["actions"]],
        {
            number: _article_id({"doc": SECTOR_LAW_CODE, "article": number}, article_ids)
            for number in SECTOR_RULE_ARTICLES.values()
        },
    )
    for rule in rules:
        rule["updated_at"] = timestamp
    return roles, actions, employees, resources, rules


def load_seed_rows(
    article_ids: dict[ArticleKey, int],
    source_hashes: dict[str, str],
    timestamp: datetime,
    seed_dir: Path = SEED_DATA_DIR,
) -> SeedRows:
    """Load all seed files and resolve their references to export IDs."""
    issuers, issuer_ids = _issuer_rows(_load(seed_dir / SEED_ISSUERS_FILE, "issuers"))
    documents, doc_ids = _document_rows(
        _load(seed_dir / SEED_DOCUMENTS_FILE, "documents"), issuer_ids, source_hashes, timestamp
    )
    relations = _relation_rows(
        _load(seed_dir / SEED_RELATIONS_FILE, "relations"), doc_ids, article_ids
    )
    procedures, requirements = _procedure_rows(
        _load(seed_dir / SEED_PROCEDURES_FILE, "procedures"), doc_ids, article_ids, timestamp
    )
    roles, actions, employees, resources, rules = _access_rows(
        seed_dir, doc_ids, article_ids, timestamp
    )
    logger.info(
        "Loaded seed data: %d issuers, %d documents, %d relations, %d procedures, "
        "%d roles, %d employees, %d resources, %d decision rules",
        len(issuers),
        len(documents),
        len(relations),
        len(procedures),
        len(roles),
        len(employees),
        len(resources),
        len(rules),
    )
    return SeedRows(
        tuple(issuers),
        tuple(documents),
        tuple(relations),
        tuple(procedures),
        tuple(requirements),
        tuple(roles),
        tuple(actions),
        tuple(employees),
        tuple(resources),
        tuple(rules),
    )
