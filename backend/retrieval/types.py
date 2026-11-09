"""Data passed between the retrieval steps."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Requester:
    """Who is asking: decides which documents are visible."""

    employee_id: str
    role_id: str
    access_level: int


@dataclass(frozen=True, slots=True)
class Candidate:
    """A chunk found by search, with its whole article and the details needed for citation.

    ``text`` is the matched clause; ``article_text`` is the full article it belongs to,
    which is what is shown and given to the answer step (a clause alone can be just an
    intro such as «المكلفون بالتبليغ عن المواليد هم:»).
    """

    chunk_id: str
    text: str
    doc_id: int
    doc_title: str
    article_id: int
    article_no: int
    article_label: str
    clause_no: int
    score: float = 0.0
    article_text: str = ""


@dataclass(frozen=True, slots=True)
class Override:
    """A relation from a newer document that changes an article or a whole document."""

    source_doc_id: int
    source_title: str
    target_doc_id: int
    target_article_id: int | None
    relation_type: str
    issuer_name: str
    referral_text: str
    # False when the system holds no text for the changing document (e.g. an amendment
    # kept only in an internal file): the article is shown with an amendment notice.
    source_held: bool = True


@dataclass(frozen=True, slots=True)
class Referral:
    """Shown instead of a rule the requester may not see the current version of.

    It names only the competent authority, never the document that changed the rule.
    """

    issuer_name: str
    referral_text: str
    article_ids: tuple[int, ...]


@dataclass(slots=True)
class RetrievalResult:
    """Articles the requester may read (one best-ranked chunk each), plus referrals for
    rules changed out of their sight."""

    chunks: list[Candidate] = field(default_factory=list)
    referrals: list[Referral] = field(default_factory=list)
    # chunk_id -> titles of documents the requester may see that changed that chunk's rule
    changed_by: dict[str, list[str]] = field(default_factory=dict)
    # chunk_id -> notice for an article amended by a text the system does not hold: the
    # article is quoted word for word with this notice and referral, never summarised.
    amended_notices: dict[str, str] = field(default_factory=dict)

    @property
    def response_type(self) -> str:
        """answer, referral or insufficient (the categories stored in query_log)."""
        if self.chunks:
            return "answer"
        return "referral" if self.referrals else "insufficient"
