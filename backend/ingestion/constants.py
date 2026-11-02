"""Paths, document metadata, and lexical constants for regulatory ingestion."""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
RAW_DATA_DIR: Final[Path] = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR: Final[Path] = PROJECT_ROOT / "data" / "processed"
EXPORT_PATH: Final[Path] = PROCESSED_DATA_DIR / "Tabayyun_KB.xlsx"
SEED_DATA_DIR: Final[Path] = PROJECT_ROOT / "data" / "seed"
# Page text cache. It is committed to git so every team member works on exactly the
# same OCR text, which the reviewed text corrections are written against.
PAGE_TEXT_CACHE_DIR: Final[Path] = PROJECT_ROOT / "data" / "ocr"
SEED_CORRECTIONS_FILE: Final[str] = "text_corrections.json"
SEED_ISSUERS_FILE: Final[str] = "issuers.json"
SEED_DOCUMENTS_FILE: Final[str] = "documents.json"
SEED_RELATIONS_FILE: Final[str] = "relations.json"
SEED_PROCEDURES_FILE: Final[str] = "procedures.json"

OCR_DPI: Final[int] = 300
OCR_LANGUAGE: Final[str] = "ara"
# psm 4 (single column of variable-size text) keeps short last lines of paragraphs
# that psm 6 silently dropped.
OCR_CONFIG: Final[str] = "--psm 4"
# A page is treated as blank only when almost no pixels are dark ("ink").
# Normal text pages are mostly white, so a white-fraction test wrongly rejects them.
OCR_INK_THRESHOLD: Final[int] = 128
OCR_MIN_INK_FRACTION: Final[float] = 0.002
OCR_MIN_TEXT_CHARACTERS: Final[int] = 50
# Text-layer PDFs are read with poppler's pdftotext, which rebuilds word spacing
# from glyph positions (PyMuPDF glues Arabic words together for this file).
PDFTOTEXT_COMMAND: Final[str] = "pdftotext"
# Private-use glyphs that the nationality PDF uses for Arabic ligatures.
TEXT_LAYER_GLYPH_FIXES: Final[tuple[tuple[str, str], ...]] = (
    ("\ue004", "لمج"),
    ("\ue005", "لمخ"),
)
TESSDATA_BEST_DIR: Final[Path] = PROJECT_ROOT / ".tessdata_best"
TESSDATA_BEST_MODEL: Final[Path] = TESSDATA_BEST_DIR / "ara.traineddata"
PAGE_BREAK_CHARACTER: Final[str] = "\f"
PAGE_SEPARATOR: Final[str] = f"\n{PAGE_BREAK_CHARACTER}\n"
TEXT_LAYER_SOURCE_FILENAMES: Final[tuple[str, ...]] = ("nationality_law_and_regulation.pdf",)
REGULATION_BOUNDARY: Final[str] = "اللائحة التنفيذية لنظام الجنسية العربية السعودية"
NATIONALITY_REGULATION_TITLE: Final[str] = REGULATION_BOUNDARY
CLAUSE_NUMBER_START: Final[int] = 1
MAX_HEADER_LINES: Final[int] = 6
DEFAULT_EXPORT_STATUS: Final[str] = "active"
APPROVER_TEXT_STOP_CHARACTERS: Final[str] = "،؛.\n"
CONDITIONAL_PROHIBITION_KEYWORDS: Final[tuple[str, str]] = ("لا يجوز", "إلا")
PUBLIC_CLASSIFICATION_LEVEL: Final[int] = 1
ARTICLE_VERSION: Final[int] = 1
MANUAL_REVIEW_NOTE: Final[str] = "Rule and procedure extraction requires manual review."


@dataclass(frozen=True, slots=True)
class DocumentSpec:
    """Describe a source document's identity and article-heading format."""

    doc_id: int
    code: str
    source_filename: str
    title: str
    doc_type: str
    article_style: str
    expected_articles: int
    header_markers: tuple[str, ...]
    first_article_anchor: str = ""
    sequential_headings: bool = False


DOCUMENT_SPECS: Final[tuple[DocumentSpec, ...]] = (
    DocumentSpec(
        doc_id=1,
        code="CSL",
        source_filename="civil_status_law.pdf",
        title="نظام الأحوال المدنية",
        doc_type="law",
        article_style="ordinal",
        expected_articles=96,
        header_markers=("نظام الأحوال المدنية",),
        sequential_headings=True,
    ),
    DocumentSpec(
        doc_id=2,
        code="CSR",
        source_filename="civil_status_regulation.pdf",
        title="اللائحة التنفيذية لنظام الأحوال المدنية",
        doc_type="regulation",
        article_style="numeric",
        expected_articles=199,
        header_markers=("اللائحة التنفيذية لنظام الأحوال المدنية",),
        sequential_headings=True,
    ),
    DocumentSpec(
        doc_id=3,
        code="NAT",
        source_filename="nationality_law_and_regulation.pdf",
        title="نظام الجنسية العربية السعودية",
        doc_type="law",
        article_style="number_suffix",
        expected_articles=30,
        header_markers=("نظام الجنسية العربية السعودية",),
        first_article_anchor="يسمى هذا النظام",
    ),
    DocumentSpec(
        doc_id=4,
        code="NATR",
        source_filename="nationality_law_and_regulation.pdf",
        title="اللائحة التنفيذية لنظام الجنسية العربية السعودية",
        doc_type="regulation",
        article_style="ordinal",
        expected_articles=35,
        header_markers=("اللائحة التنفيذية لنظام الجنسية العربية السعودية",),
    ),
)

SOURCE_FILENAMES: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(spec.source_filename for spec in DOCUMENT_SPECS)
)

HEADER_LINE: Final[str] = "الإدارة القانونية"
ARTICLE_PREFIX: Final[str] = "المادة"
PAGE_COUNTER_PATTERN: Final[str] = r"^\s*\d+\s+من\s+\d+\s*$"
# OCR often garbles the page counter at the bottom of a page ("٣ من ٢٧" read as
# "؛؟ من 77" or "من لاا"): a short last line with "من" and almost no letters.
PAGE_COUNTER_WORD: Final[str] = "من"
PAGE_COUNTER_MAX_LENGTH: Final[int] = 16
PAGE_COUNTER_MAX_OTHER_LETTERS: Final[int] = 3
# Letters OCR produces from the counter digits; a counter without digits may only use these.
PAGE_COUNTER_NOISE_LETTERS: Final[str] = "لايد"
# Lines starting with "المادة" always start a new paragraph when wrapped lines are joined
# (this covers text-layer headings such as "المادةالأولى" with no space).
ARTICLE_LINE_PATTERN: Final[str] = r"^\s*المادة"
# Article-heading detection for OCR'd documents (see headings.py).
# OCR misreads the digits inside headings and sometimes reverses the line direction,
# so a heading is recognised by the word "المادة" at either end of a short line.
HEADING_WORD_PATTERN: Final[str] = r"^[^\u0621-\u064A]*(?:ال)?ماد[ةه](?P<tail>[^\u0621-\u064A]*)$"
HEADING_MAX_WORDS: Final[int] = 4
HEADING_TAIL_SENTENCE_END: Final[str] = r"[.،:؛]"
HEADING_STRIP_CHARACTERS: Final[str] = ".,،:؛()*+/\\"
# Words that show the line is an in-text reference ("المادة (15) من النظام") or an
# amendment marker ("تعديلات المادة الثانية"), not a heading.
HEADING_EXCLUDED_WORDS: Final[frozenset[str]] = frozenset(
    {"من", "في", "فى", "النظام", "اللائحة", "هذه", "هذا"}
)
HEADING_EXCLUDED_SUBSTRINGS: Final[tuple[str, ...]] = ("تعديل",)
NUMERIC_HEADING_PATTERN: Final[str] = (
    r"(?m)^[ \t]*المادة[ \t]*[()\[\]{}]?[ \t]*/?[ \t]*[()\[\]{}]?"
    r"[ \t]*(?P<number>[^()\s/]{1,3})[ \t]*[()\[\]{}]?[ \t]*"
    r"[\u064b-\u065f]*[ \t]*$"
)
ORDINAL_HEADING_PATTERN: Final[str] = (
    r"(?m)^[ \t]*المادة[ \t]*/?[ \t]*(?P<ordinal>[\u0621-\u064Aـ]+"
    r"(?:[ \t]+(?:و)?[\u0621-\u064Aـ]+){0,3})[ \t]*$"
)
# Nationality law (pdftotext): each article number is printed on its own line
# ("-12") right after the FIRST line of that article.
NUMBER_MARKER_LINE_PATTERN: Final[str] = r"^\s*[-–—]\s*(?P<number>\d{1,3})\s*[-–—]?\s*$"
# "*تعديلات المادة الثانية" (OCR may read the star as # or «) or "* (1)". The ordinal
# after "المادة" is limited to three words so following text is never removed.
AMENDMENT_MARKER_PATTERN: Final[str] = (
    r"[*#«»]*\s*(?P<marker>تعديلات\s+المادة(?:\s+[\u0621-\u064A]+){1,3})"
    r"|[*#]+\s*(?P<number_marker>\(\s*\d+\s*\))"
)
PUNCTUATION_PATTERN: Final[str] = r"[!\"#$%&'()*+,-./:;<=>?@\[\]\\^_`{|}~،؛؟«»ـ]"
FORMATTING_CHARACTERS: Final[str] = "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff"
COMMON_OCR_REPLACEMENTS: Final[tuple[tuple[str, str], ...]] = (("»", "،"),)
STRAY_LINE_END_MARKER_PATTERN: Final[str] = r"(?:[ \t]+[0-9*†‡]{1,2})+[ \t]*$"

ARABIC_DIGITS: Final[str] = "٠١٢٣٤٥٦٧٨٩"
WESTERN_DIGITS: Final[str] = "0123456789"

ORDINAL_ONES: Final[tuple[str, ...]] = (
    "الأولى",
    "الثانية",
    "الثالثة",
    "الرابعة",
    "الخامسة",
    "السادسة",
    "السابعة",
    "الثامنة",
    "التاسعة",
    "العاشرة",
)
ORDINAL_COMPOUND_ONES: Final[tuple[str, ...]] = (
    "الحادية",
    "الثانية",
    "الثالثة",
    "الرابعة",
    "الخامسة",
    "السادسة",
    "السابعة",
    "الثامنة",
    "التاسعة",
)
ORDINAL_TEENS: Final[tuple[str, ...]] = (
    "الحادية عشرة",
    "الثانية عشرة",
    "الثالثة عشرة",
    "الرابعة عشرة",
    "الخامسة عشرة",
    "السادسة عشرة",
    "السابعة عشرة",
    "الثامنة عشرة",
    "التاسعة عشرة",
)
ORDINAL_TEENS_MASCULINE: Final[tuple[str, ...]] = (
    "الحادية عشر",
    "الثانية عشر",
    "الثالثة عشر",
    "الرابعة عشر",
    "الخامسة عشر",
    "السادسة عشر",
    "السابعة عشر",
    "الثامنة عشر",
    "التاسعة عشر",
)
ORDINAL_TENS: Final[tuple[str, ...]] = (
    "العشرون",
    "الثلاثون",
    "الأربعون",
    "الخمسون",
    "الستون",
    "السبعون",
    "الثمانون",
    "التسعون",
)
CLAUSE_LETTERS: Final[tuple[str, ...]] = ("أ", "ا", "ب", "ت", "ث", "ج", "جـ", "د", "هـ", "و")


APPROVAL_PHRASES: Final[tuple[str, ...]] = (
    "بقرار من",
    "بموافقة",
    "يرفع إلى",
    "يحال إلى",
    "بعد صدور قرار من",
)

RULE_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "تعريف": ("يقصد", "تدل المصطلحات"),
    "عقوبة": ("يعاقب", "غرامة"),
    "منع مشروط": ("لا يجوز", "إلا"),
    "منع": ("لا يجوز", "يحظر", "يعتبر سريا"),
    "إلزام": ("يجب", "على أن"),
    "إجازة": ("يجوز", "له أن"),
}

ARTICLE_STATUS_AMENDED: Final[str] = "amended"
DEFAULT_RULE_TYPE: Final[str] = "إجرائي"
# Checked before the "earliest keyword wins" rule in classify_rule_type.
PRIORITY_RULE_TYPES: Final[tuple[str, ...]] = ("تعريف", "عقوبة", "منع مشروط")
PROCEDURE_REVIEW_DRAFT: Final[str] = "draft"


EXPORT_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "issuers": ("issuer_id", "name", "issuer_type", "referral_text"),
    "documents": (
        "doc_id",
        "doc_type",
        "title",
        "doc_number",
        "issuer_id",
        "issue_date_hijri",
        "issue_date",
        "effective_from",
        "effective_to",
        "status",
        "classification_level",
        "source_url",
        "file_path",
        "content_hash",
        "created_at",
        "updated_at",
    ),
    "articles": (
        "article_id",
        "doc_id",
        "article_no",
        "article_label",
        "text",
        "status",
        "effective_from",
        "effective_to",
        "classification_level",
        "rule_type",
        "requires_approval",
        "approver_text",
        "version_no",
        "created_at",
        "updated_at",
    ),
    "chunks": (
        "chunk_id",
        "article_id",
        "doc_id",
        "clause_no",
        "text",
        "text_normalized",
        "classification_level",
        "is_current",
        "created_at",
    ),
    "document_relations": (
        "relation_id",
        "source_doc_id",
        "source_article_id",
        "target_doc_id",
        "target_article_id",
        "relation_type",
        "effective_from",
        "notes",
    ),
    "procedures": (
        "procedure_id",
        "name",
        "aliases",
        "description",
        "responsible_department",
        "source_doc_id",
        "source_article_id",
        "status",
        "review_status",
        "updated_at",
    ),
    "procedure_requirements": (
        "requirement_id",
        "procedure_id",
        "requirement_type",
        "name",
        "description",
        "is_mandatory",
        "source_article_id",
        "order_no",
    ),
    "validation": (
        "document_code",
        "doc_id",
        "expected_articles",
        "actual_articles",
        "missing_numbers",
        "duplicate_numbers",
        "unexpected_numbers",
        "heading_disagreements",
        "extra_heading_pages",
        "missing_heading_pages",
        "missing_heading_near_page",
        "shortest_article_no",
        "shortest_characters",
        "longest_article_no",
        "longest_characters",
        "problems",
    ),
    "amendment_markers": ("article_no", "marker_text"),
}
