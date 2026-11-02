"""Paths, document metadata, and lexical constants for regulatory ingestion."""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
RAW_DATA_DIR: Final[Path] = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR: Final[Path] = PROJECT_ROOT / "data" / "processed"
EXPORT_PATH: Final[Path] = PROCESSED_DATA_DIR / "Tabayyun_KB.xlsx"

OCR_DPI: Final[int] = 300
OCR_LANGUAGE: Final[str] = "ara"
OCR_CONFIG: Final[str] = "--psm 6"
OCR_IMAGE_WHITE_THRESHOLD: Final[int] = 250
OCR_IMAGE_WHITE_FRACTION: Final[float] = 0.995
OCR_MIN_TEXT_CHARACTERS: Final[int] = 50
OCR_TEXT_SUFFIX: Final[str] = ".txt"
TESSDATA_BEST_DIR: Final[Path] = PROJECT_ROOT / ".tessdata_best"
TESSDATA_BEST_MODEL: Final[Path] = TESSDATA_BEST_DIR / "ara.traineddata"
PAGE_BREAK_CHARACTER: Final[str] = "\f"
PAGE_SEPARATOR: Final[str] = f"\n{PAGE_BREAK_CHARACTER}\n"
TEXT_LAYER_SOURCE_FILENAMES: Final[tuple[str, ...]] = ("nationality_law_and_regulation.pdf",)
NATIONALITY_TEXT_CODE: Final[str] = "NAT"
NATIONALITY_REGULATION_CODE: Final[str] = "NATR"
NATIONALITY_LAW_ARTICLE_MAX: Final[int] = 30
REGULATION_BOUNDARY: Final[str] = "اللائحة التنفيذية لنظام الجنسية العربية السعودية"
NATIONALITY_REGULATION_TITLE: Final[str] = REGULATION_BOUNDARY
CLAUSE_NUMBER_START: Final[int] = 1
REGULATION_DOCUMENT_ID: Final[int] = 2
NATIONALITY_LAW_DOCUMENT_ID: Final[int] = 3
MAX_HEADER_LINES: Final[int] = 6
DEFAULT_EXPORT_STATUS: Final[str] = "active"
DEFAULT_DOCUMENT_NUMBER: Final[str] = ""
DEFAULT_SOURCE_URL: Final[str] = ""
DEFAULT_RESPONSIBLE_DEPARTMENT: Final[str] = ""
DEFAULT_ARTICLE_DATE: Final[str] = ""
DECISION_CONTEXT_CHARACTERS: Final[int] = 140
DECISION_NUMBER_PATTERN: Final[str] = (
    r"(?:القرار الوزاري|قرار وزاري)\s*(?:رقم\s*)?[()\[\]{}]?\s*"
    r"(?P<number>\d+(?:\s*/\s*(?:\d+|وز)){0,2})(?!\w|/|\s+\d)"
)
APPROVER_TEXT_STOP_CHARACTERS: Final[str] = "،؛.\n"
PROCEDURE_MANDATORY_KEYWORDS: Final[tuple[str, ...]] = ("يجب", "يشترط", "يتعين")
CONDITIONAL_PROHIBITION_KEYWORDS: Final[tuple[str, str]] = ("لا يجوز", "إلا")
REQUIREMENT_STATEMENT_TYPE: Final[str] = "statement"
DOCUMENT_CODE_CIVIL_REGULATION: Final[str] = "CSR"
AMENDMENT_MARKER_WORD: Final[str] = "تعديلات"
LEGACY_NATIONALITY_LAW_TITLE: Final[str] = "نظام الجنسية العربية السعودية"
LEGACY_NATIONALITY_ARTICLE_NO: Final[int] = 28
PUBLIC_CLASSIFICATION_LEVEL: Final[int] = 1
ARTICLE_VERSION: Final[int] = 1
DEFAULT_ISSUER_REFERRAL: Final[str] = ""
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
ARTICLE_LINE_PATTERN: Final[str] = r"^\s*المادة"
NUMERIC_HEADING_PATTERN: Final[str] = (
    r"(?m)^[ \t]*المادة[ \t]*[()\[\]{}]?[ \t]*/?[ \t]*[()\[\]{}]?"
    r"[ \t]*(?P<number>[^()\s/]{1,3})[ \t]*[()\[\]{}]?[ \t]*"
    r"[\u064b-\u065f]*[ \t]*$"
)
ORDINAL_HEADING_PATTERN: Final[str] = (
    r"(?m)^[ \t]*المادة[ \t]*/?[ \t]*(?P<ordinal>[\u0621-\u064Aـ]+"
    r"(?:[ \t]+(?:و)?[\u0621-\u064Aـ]+){0,3})[ \t]*$"
)
NUMBER_SUFFIX_PATTERN: Final[str] = r"(?m)[-–—]\s*(?P<number>\d{1,3})(?:\s*[-–—])?(?!\d)"
AMENDMENT_MARKER_PATTERN: Final[str] = r"\*+\s*(?P<marker>تعديلات\s+المادة\s+[^\n*]+|\(\s*\d+\s*\))"
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

ISSUER_NAMES: Final[tuple[str, ...]] = (
    "مجلس الوزراء",
    "وزير الداخلية",
    "وكالة وزارة الداخلية للأحوال المدنية",
    "المديرية العامة للأحوال المدنية",
    "إدارة الأحوال المدنية",
    "اللجنة المحلية",
    "اللجنة الفرعية",
    "هيئة الأحوال المدنية المركزية",
    "الإدارة العامة بالمنطقة",
    "ديوان المظالم",
)

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

PROCEDURE_START_PHRASES: Final[tuple[str, ...]] = (
    "عند طلب",
    "يجوز",
    "يشترط",
    "يتعين",
    "تقدم طلب",
    "يقدم طلب",
)
PROCEDURE_NAME_MAX_LENGTH: Final[int] = 140
DOCUMENT_STATUS_ACTIVE: Final[str] = "active"
DOCUMENT_STATUS_REPEALED: Final[str] = "repealed"
ISSUER_TYPE_EXECUTIVE: Final[str] = "executive"
ISSUER_TYPE_INTERNAL: Final[str] = "internal"
RELATION_AMENDS: Final[str] = "amends"
RELATION_REPEALS: Final[str] = "repeals"
RELATION_REPLACES: Final[str] = "replaces"
LEGACY_NATIONALITY_ARTICLE_NO: Final[int] = 28
PROCEDURE_REVIEW_DRAFT: Final[str] = "draft"
PROCEDURE_REQUIREMENT_TYPE_ORDER: Final[tuple[str, ...]] = (
    "document",
    "condition",
    "deadline",
    "fee",
    "statement",
)
REQUIREMENT_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "document": ("إرفاق", "مستند", "شهادة", "وثيقة", "صورة", "جواز"),
    "deadline": ("خلال", "مدة", "يوم", "أيام", "شهر", "سنة", "أسبوع"),
    "fee": ("رسم", "رسوم"),
    "condition": ("إذا", "يشترط", "شرط", "على أن"),
}

REFERENCED_LEGAL_TITLES: Final[tuple[tuple[str, str], ...]] = (
    ("نظام دائرة النفوس", "repealed"),
    ("نظام المواليد والوفيات", "repealed"),
)

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
