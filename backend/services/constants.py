"""Constants for the access decision matrix."""

from typing import Final

DECISION_ALLOWED: Final[str] = "allowed"
DECISION_DENIED: Final[str] = "denied"
DECISION_REQUIRES_APPROVAL: Final[str] = "requires_approval"

ACTION_VIEW: Final[str] = "A1"
ACTION_DOWNLOAD: Final[str] = "A2"
ACTION_EDIT: Final[str] = "A3"
ACTION_SHARE: Final[str] = "A4"

PUBLIC_LEVEL: Final[int] = 1
DENY_LEVEL_GAP: Final[int] = 2
CLASSIFICATION_NAMES: Final[dict[int, str]] = {1: "عام", 2: "مقيّد", 3: "سري", 4: "سري للغاية"}

# Sector rules from the Civil Status Law, attached to resources in data/seed/resources.json.
RULE_NO_TRANSFER: Final[str] = "no_transfer"
RULE_COMMITTEE_EDIT: Final[str] = "committee_edit"
RULE_OFFICIAL_COPY: Final[str] = "official_copy"
SECTOR_LAW_CODE: Final[str] = "CSL"
SECTOR_RULE_ARTICLES: Final[dict[str, int]] = {
    RULE_NO_TRANSFER: 11,
    RULE_COMMITTEE_EDIT: 15,
    RULE_OFFICIAL_COPY: 23,
}
COMMITTEE_ROLE_ID: Final[str] = "R5"
DEFAULT_APPROVER_ROLE_ID: Final[str] = "R3"
TOP_APPROVER_NAME: Final[str] = "المديرية العامة للأحوال المدنية"

SOURCE_GENERAL: Final[str] = (
    "قاعدة عامة: مبدأ الحاجة إلى المعرفة ومبدأ الحد الأدنى من الصلاحيات "
    "(سياسة تصنيف البيانات، سدايا 2021، المبدآن السادس والسابع)"
)
SOURCE_SECTOR: Final[str] = "حكم نظامي خاص: نظام الأحوال المدنية، المادة {article}"
