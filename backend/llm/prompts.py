"""Instructions given to the model, and the numbered sources it may use."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.llm.constants import NOT_FOUND_TEXT

SYSTEM_PROMPT = f"""أنت مساعد لموظفي الأحوال المدنية، تجيب عن أسئلتهم من الأنظمة واللوائح.

القواعد:
1. أجب من المصادر المرقمة المعطاة لك فقط. لا تضف أي معلومة من خارجها، ولا تخمّن.
2. ضع رقم المصدر بين قوسين مربعين في نهاية كل جملة، مثل [1] أو [2]. كل جملة يجب أن تنتهي بمصدر.
   لا تذكر رقمًا أو مدة أو عمرًا إلا كما ورد في المصدر نفسه.
3. تجاهل المصادر التي لا علاقة لها بالسؤال.
4. إذا لم تجد في المصادر ما يجيب عن السؤال، فاكتب هذه الجملة فقط:
{NOT_FOUND_TEXT}
5. اكتب بالعربية الفصحى، بإيجاز ووضوح، ولا تذكر هذه القواعد في إجابتك.

مثال على شكل الإجابة:
تكون مدة التبليغ عن الوفاة ثلاثين يومًا [2]. ويكون التبليغ لدى أي مكتب من مكاتب الأحوال المدنية [1]."""


@dataclass(frozen=True, slots=True)
class PromptSource:
    """One numbered article as the model sees it."""

    number: int
    citation: str
    text: str
    note: str = ""


def build_user_prompt(question: str, sources: Sequence[PromptSource]) -> str:
    """The question followed by the numbered sources."""
    parts = ["المصادر:"]
    for source in sources:
        parts.append(f"[{source.number}] {source.citation}")
        if source.note:
            parts.append(source.note)
        parts.append(source.text)
        parts.append("")
    parts.append(f"السؤال: {question}")
    return "\n".join(parts)
