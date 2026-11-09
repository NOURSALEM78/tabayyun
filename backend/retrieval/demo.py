"""Load or remove the fictional test circular used to try the referral rule.

``python -m backend.retrieval.demo`` loads it (re-running replaces it); then run
``python -m backend.retrieval.embed`` to embed its text.
``python -m backend.retrieval.demo --remove`` deletes it and everything attached.

The circular is marked as a test in its number (تجريبي-1), title and text, so it
is never mistaken for a real document. No column or flag is added for this.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, delete, func, select

from backend.db.database import engine
from backend.db.models import (
    Article,
    Chunk,
    Document,
    DocumentAccess,
    DocumentRelation,
    Issuer,
)
from backend.ingestion.constants import DOCUMENT_SPECS, PROJECT_ROOT
from backend.ingestion.normalize import normalize_arabic

logger = logging.getLogger(__name__)
DEMO_FILE = PROJECT_ROOT / "data" / "demo" / "secret_circular.json"
ISSUER_NAMES = {"civil_affairs_agency": "وكالة وزارة الداخلية للأحوال المدنية"}


def remove_demo(connection: Connection, doc_number: str) -> int:
    """Delete the test circular and everything attached to it; return how many were removed."""
    doc_ids = list(
        connection.scalars(select(Document.doc_id).where(Document.doc_number == doc_number))
    )
    if not doc_ids:
        return 0
    connection.execute(delete(DocumentAccess).where(DocumentAccess.doc_id.in_(doc_ids)))
    connection.execute(delete(DocumentRelation).where(DocumentRelation.source_doc_id.in_(doc_ids)))
    connection.execute(delete(Chunk).where(Chunk.doc_id.in_(doc_ids)))
    connection.execute(delete(Article).where(Article.doc_id.in_(doc_ids)))
    connection.execute(delete(Document).where(Document.doc_id.in_(doc_ids)))
    return len(doc_ids)


def _next_id(connection: Connection, column: Any) -> int:
    return (connection.scalar(select(func.max(column))) or 0) + 1


def load_demo(connection: Connection, data: dict[str, Any]) -> int:
    """Insert the circular, its article and chunk, the amends relation and its access list."""
    meta, article = data["document"], data["article"]
    remove_demo(connection, meta["doc_number"])
    issuer_id = connection.scalar(
        select(Issuer.issuer_id).where(Issuer.name == ISSUER_NAMES[meta["issuer_key"]])
    )
    target_spec = next(spec for spec in DOCUMENT_SPECS if spec.code == data["amends"]["doc"])
    target_article = connection.scalar(
        select(Article.article_id).where(
            Article.doc_id == target_spec.doc_id, Article.article_no == data["amends"]["article"]
        )
    )
    doc_id = _next_id(connection, Document.doc_id)
    article_id = _next_id(connection, Article.article_id)
    connection.execute(
        Document.__table__.insert().values(
            doc_id=doc_id,
            doc_type=meta["doc_type"],
            title=meta["title"],
            doc_number=meta["doc_number"],
            issuer_id=issuer_id,
            status="active",
            classification_level=meta["classification_level"],
            source_url=meta["source_url"],
        )
    )
    connection.execute(
        Article.__table__.insert().values(
            article_id=article_id,
            doc_id=doc_id,
            article_no=article["article_no"],
            article_label=article["article_label"],
            text=article["text"],
            status="active",
            classification_level=meta["classification_level"],
            rule_type="إلزام",
            requires_approval=False,
            version_no=1,
        )
    )
    connection.execute(
        Chunk.__table__.insert().values(
            chunk_id=f"{meta['doc_number']}-A{article['article_no']:03d}-C01",
            article_id=article_id,
            doc_id=doc_id,
            clause_no=1,
            text=article["text"],
            text_normalized=normalize_arabic(article["text"]),
            classification_level=meta["classification_level"],
            is_current=True,
        )
    )
    relation_id = _next_id(connection, DocumentRelation.relation_id)
    connection.execute(
        DocumentRelation.__table__.insert().values(
            relation_id=relation_id,
            source_doc_id=doc_id,
            source_article_id=article_id,
            target_doc_id=target_spec.doc_id,
            target_article_id=target_article,
            relation_type="amends",
            notes="Test circular (تجريبي) for checking referrals; not a real document.",
        )
    )
    access_id = _next_id(connection, DocumentAccess.id)
    for offset, role_id in enumerate(data["visible_to_roles"]):
        connection.execute(
            DocumentAccess.__table__.insert().values(
                id=access_id + offset, doc_id=doc_id, role_id=role_id
            )
        )
    return doc_id


def main() -> None:
    """Load the test circular, or remove it with --remove."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Load or remove the test circular.")
    parser.add_argument("--remove", action="store_true", help="delete the test circular")
    arguments = parser.parse_args()
    data = json.loads(Path(DEMO_FILE).read_text(encoding="utf-8"))
    with engine.begin() as connection:
        if arguments.remove:
            removed = remove_demo(connection, data["document"]["doc_number"])
            logger.info("Removed %d test circular(s)", removed)
            return
        doc_id = load_demo(connection, data)
    logger.info("Test circular loaded as document %d", doc_id)
    logger.info("Next: python -m backend.retrieval.embed")


if __name__ == "__main__":
    main()
