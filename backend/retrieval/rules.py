"""Pure retrieval rules: rank fusion, the secret-amendment referral and amendment notices."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import replace

from backend.retrieval.constants import AMENDED_NOTICE, RRF_K
from backend.retrieval.types import Candidate, Override, Referral, RetrievalResult


def fuse_rankings(rankings: Sequence[Sequence[Candidate]], k: int = RRF_K) -> list[Candidate]:
    """Merge ranked lists with reciprocal rank fusion: score = sum of 1 / (k + rank)."""
    scores: dict[str, float] = defaultdict(float)
    first_seen: dict[str, Candidate] = {}
    for ranking in rankings:
        for rank, candidate in enumerate(ranking, start=1):
            scores[candidate.chunk_id] += 1.0 / (k + rank)
            first_seen.setdefault(candidate.chunk_id, candidate)
    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))
    return [_with_score(first_seen[chunk_id], scores[chunk_id]) for chunk_id in ordered]


def _with_score(candidate: Candidate, score: float) -> Candidate:
    """Return a copy of the candidate carrying its fused score."""
    return replace(candidate, score=score)


def _is_secret(override: Override, visible_doc_ids: set[int]) -> bool:
    """The changing document is one the requester may not see."""
    return override.source_doc_id not in visible_doc_ids


def _is_unheld(override: Override, visible_doc_ids: set[int]) -> bool:
    """A visible change to a named article whose text the system does not hold."""
    return (
        not _is_secret(override, visible_doc_ids)
        and override.target_article_id is not None
        and not override.source_held
    )


def _applies_to(override: Override, candidate: Candidate) -> bool:
    """An override targets one article, or the whole document when no article is given."""
    if override.target_doc_id != candidate.doc_id:
        return False
    return override.target_article_id in (None, candidate.article_id)


def _notice(override: Override) -> str:
    """The amendment notice followed by the issuer's referral text."""
    return f"{AMENDED_NOTICE} {override.referral_text}"


def apply_overrides(
    candidates: Iterable[Candidate],
    overrides: Sequence[Override],
    visible_doc_ids: set[int],
    limit: int,
) -> RetrievalResult:
    """Keep the chunks whose rule may be shown to this requester.

    * Changed by a document the requester may not see (a secret circular): the chunk is
      dropped and a referral to the issuer is returned instead, so no possibly outdated
      rule is given and the changing document is not named.
    * Changed by an amendment whose text the system does not hold (law articles marked
      «تعديلات المادة» whose amendment file is internal): the chunk is kept, and
      ``amended_notices`` carries a notice that the article was amended plus the
      issuer's referral. The answer must quote the article word for word.
    * Changed by a document the requester may see and the system holds: the chunk is
      kept. When the change names this article, the newer document's title is recorded
      in ``changed_by`` (its own text is searchable too). Whole-document amendments
      that are public are already part of the published text, so they add no note.

    Candidates are read in rank order and reading stops once ``limit`` chunks are
    kept, so only overrides on well-ranked chunks produce referrals.
    """
    result = RetrievalResult()
    referrals: dict[str, list[int]] = {}
    texts: dict[str, str] = {}
    for candidate in candidates:
        if len(result.chunks) >= limit:
            break
        applying = [override for override in overrides if _applies_to(override, candidate)]
        secret = [override for override in applying if _is_secret(override, visible_doc_ids)]
        if secret:
            for override in secret:
                referrals.setdefault(override.issuer_name, []).append(candidate.article_id)
                texts[override.issuer_name] = override.referral_text
            continue
        unheld = [override for override in applying if _is_unheld(override, visible_doc_ids)]
        noted = [
            override
            for override in applying
            if override.target_article_id is not None and override.source_held
        ]
        if unheld:
            result.amended_notices[candidate.chunk_id] = _notice(unheld[0])
        if noted:
            result.changed_by[candidate.chunk_id] = sorted({o.source_title for o in noted})
        result.chunks.append(candidate)
    result.referrals = [
        Referral(name, texts[name], tuple(sorted(set(article_ids))))
        for name, article_ids in referrals.items()
    ]
    return result
