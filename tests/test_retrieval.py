"""Tests for rank fusion, the override rules (secret amendments, amendment notices) and keyword search."""

from __future__ import annotations

from backend.retrieval.constants import AMENDED_NOTICE
from backend.retrieval.keyword import KeywordIndex, tokenize
from backend.retrieval.rules import apply_overrides, fuse_rankings
from backend.retrieval.types import Candidate, Override


def candidate(chunk_id: str, doc_id: int = 2, article_id: int = 87) -> Candidate:
    return Candidate(chunk_id, "نص", doc_id, "اللائحة", article_id, article_id, "المادة", 1)


def override(
    source: int, article: int | None = 87, title: str = "تعميم", held: bool = True
) -> Override:
    return Override(
        source, title, 2, article, "amends", "الوكالة", "يُرجى الرجوع إلى الوكالة.", held
    )


def test_fusion_rewards_chunks_found_by_both_methods() -> None:
    a, b, c = candidate("A"), candidate("B"), candidate("C")
    fused = fuse_rankings([[a, b], [c, b]])

    assert fused[0].chunk_id == "B"
    assert {item.chunk_id for item in fused} == {"A", "B", "C"}
    assert fused[0].score > fused[1].score


def test_hidden_amendment_drops_old_rule_and_refers_without_naming_the_document() -> None:
    result = apply_overrides(
        [candidate("A87"), candidate("A88", article_id=88)],
        [override(12)],
        visible_doc_ids={2},
        limit=5,
    )

    assert [chunk.chunk_id for chunk in result.chunks] == ["A88"]
    assert len(result.referrals) == 1
    assert result.referrals[0].issuer_name == "الوكالة"
    assert "تعميم" not in result.referrals[0].referral_text
    assert result.response_type == "answer"


def test_visible_amendment_keeps_rule_and_notes_the_newer_document() -> None:
    result = apply_overrides(
        [candidate("A87")], [override(12, title="تعميم المواليد")], visible_doc_ids={2, 12}, limit=5
    )

    assert [chunk.chunk_id for chunk in result.chunks] == ["A87"]
    assert result.referrals == []
    assert result.changed_by == {"A87": ["تعميم المواليد"]}


def test_public_whole_document_amendment_adds_no_note() -> None:
    result = apply_overrides(
        [candidate("A1", article_id=1)],
        [override(6, article=None)],
        visible_doc_ids={2, 6},
        limit=5,
    )

    assert result.changed_by == {}


def test_document_level_hidden_change_covers_every_article() -> None:
    result = apply_overrides(
        [candidate("A1", article_id=1)], [override(12, article=None)], visible_doc_ids={2}, limit=5
    )

    assert result.chunks == []
    assert result.response_type == "referral"


def test_only_well_ranked_chunks_produce_referrals() -> None:
    ranked = [candidate("A1", article_id=1), candidate("A87")]
    result = apply_overrides(ranked, [override(12)], visible_doc_ids={2}, limit=1)

    assert [chunk.chunk_id for chunk in result.chunks] == ["A1"]
    assert result.referrals == []


def test_unheld_article_amendment_keeps_text_with_notice_and_referral() -> None:
    """An article amended in a file the system lacks is quoted with a notice, not dropped."""
    result = apply_overrides(
        [candidate("A87")], [override(20, held=False)], visible_doc_ids={2, 20}, limit=5
    )

    assert [chunk.chunk_id for chunk in result.chunks] == ["A87"]
    assert result.amended_notices["A87"].startswith(AMENDED_NOTICE)
    assert result.amended_notices["A87"].endswith("يُرجى الرجوع إلى الوكالة.")
    assert result.referrals == []
    assert result.changed_by == {}


def test_secret_change_wins_over_amendment_notice() -> None:
    """If a secret document also changed the article, only the referral is given."""
    result = apply_overrides(
        [candidate("A87")],
        [override(20, held=False), override(12)],
        visible_doc_ids={2, 20},
        limit=5,
    )

    assert result.chunks == []
    assert result.amended_notices == {}
    assert result.response_type == "referral"


def test_unheld_whole_document_amendment_does_not_hide_every_article() -> None:
    """Public decisions that amend the regulation as a whole are already in its text."""
    result = apply_overrides(
        [candidate("A1", article_id=1)],
        [override(6, article=None, held=False)],
        visible_doc_ids={2, 6},
        limit=5,
    )

    assert [chunk.chunk_id for chunk in result.chunks] == ["A1"]
    assert result.amended_notices == {}


def test_each_article_is_kept_once_and_limit_counts_articles() -> None:
    """A second clause of an article already kept is skipped and does not use up the limit."""
    ranked = [
        candidate("A87-1"),
        candidate("A87-2"),
        candidate("A88-1", article_id=88),
        candidate("A89-1", article_id=89),
    ]
    result = apply_overrides(ranked, [], visible_doc_ids={2}, limit=2)

    assert [chunk.chunk_id for chunk in result.chunks] == ["A87-1", "A88-1"]


def test_nothing_found_is_insufficient() -> None:
    assert apply_overrides([], [], set(), 5).response_type == "insufficient"


def test_keyword_search_normalises_and_respects_allowed_ids() -> None:
    index = KeywordIndex(
        [
            ("C1", " ".join(tokenize("مدة التبليغ عن المواليد"))),
            ("C2", " ".join(tokenize("تجديد الهوية الوطنية"))),
            ("C3", " ".join(tokenize("قيد واقعة الزواج"))),
        ]
    )

    assert index.search("التبليغ عن المواليد", {"C1", "C2"}, 5) == ["C1"]
    assert index.search("التبليغ عن المواليد", {"C2"}, 5) == []
    assert index.search("", {"C1"}, 5) == []
