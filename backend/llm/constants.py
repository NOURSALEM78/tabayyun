"""Fixed texts and defaults for the answer step."""

from typing import Final

# Shown when the retrieved articles do not answer the question. The model is told to
# reply with exactly this sentence, so the code can recognise it.
NOT_FOUND_TEXT: Final[str] = "لم أجد في الأنظمة المتاحة نصًا يجيب عن هذا السؤال."

# Low temperature: the answer should follow the sources, not vary between runs.
LLM_TEMPERATURE: Final[float] = 0.1

# Shown instead of a model answer that failed the grounding checks (backend/llm/verify.py),
# followed by the retrieved articles word for word.
UNVERIFIED_TEXT: Final[str] = (
    "تعذّر توليد إجابة موثّقة بالمصادر لهذا السؤال. هذه أقرب المواد إليه كما وردت:"
)

AMENDED_TEXT_PREFIX: Final[str] = "نص المادة كما ورد"
REFERRAL_PREFIX: Final[str] = "إحالة"
SOURCES_HEADING: Final[str] = "المصادر"
AMENDED_LABEL: Final[str] = "(معدّلة)"
