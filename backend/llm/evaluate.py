"""Run the fixed test questions against the configured model and save every result.

Run with ``python -m backend.llm.evaluate`` (or ``--only Q01 Q02``). Each run writes
``results/<model>-<time>.jsonl`` (one line per question: retrieved and cited articles,
the model's raw reply, whether the checks rejected it, the reply shown and the time)
and prints a summary. Results are saved after every question, so a run that stops
part-way keeps what it finished.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from collections.abc import Sequence
from pathlib import Path

from backend.llm.answer import Answer, compose_answer, render
from backend.llm.client import LLMError, OpenAICompatibleModel
from backend.retrieval.embed import SentenceTransformerEncoder
from backend.retrieval.search import Retriever
from backend.retrieval.types import RetrievalResult
from backend.settings import settings

logger = logging.getLogger(__name__)

QUESTIONS_FILE = Path("data/eval/questions.json")
RESULTS_DIR = Path("results")


def article_refs(result: RetrievalResult) -> list[str]:
    """«document title:article number» for each retrieved article, in rank order."""
    return [f"{chunk.doc_title}:{chunk.article_no}" for chunk in result.chunks]


def score(case: dict, result: RetrievalResult, answer: Answer) -> dict[str, object]:
    """Compare one reply with what the question expects."""
    expected = [f"{item['doc']}:{item['article']}" for item in case["expected"]]
    retrieved = article_refs(result)
    numbered = dict(enumerate(retrieved, start=1))
    cited = [numbered[source.number] for source in answer.sources if source.number in numbered]
    return {
        "expected_retrieved": bool(set(expected) & set(retrieved)) if expected else None,
        "expected_cited": bool(set(expected) & set(cited)) if expected else None,
        "type_ok": answer.response_type == case["expect"],
        "retrieved": retrieved,
        "cited": cited,
    }


def run(cases: Sequence[dict], out_path: Path) -> list[dict[str, object]]:
    """Answer every case, appending one JSON line per case to out_path."""
    model = OpenAICompatibleModel(
        settings.llm_base_url,
        settings.llm_model,
        settings.llm_api_key,
        settings.llm_timeout,
        settings.llm_reasoning_effort,
    )
    retriever = Retriever(SentenceTransformerEncoder())
    rows: list[dict[str, object]] = []
    for case in cases:
        result = retriever.retrieve(case["question"], case["employee"])
        started = time.monotonic()
        try:
            answer = compose_answer(case["question"], result, model)
            error = ""
        except LLMError as failure:
            answer, error = Answer(), str(failure)
        row: dict[str, object] = {
            "id": case["id"],
            "question": case["question"],
            "model": settings.llm_model,
            "seconds": round(time.monotonic() - started, 1),
            "response_type": answer.response_type,
            "expect": case["expect"],
            "shown_model_answer": bool(answer.raw_reply) and not answer.rejected_reason,
            "rejected_reason": answer.rejected_reason,
            "error": error,
            "raw_reply": answer.raw_reply,
            "reply": render(answer),
            **score(case, result, answer),
        }
        rows.append(row)
        with out_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        logger.info("%s done in %ss: %s", case["id"], row["seconds"], row["response_type"])
    return rows


def summary(rows: Sequence[dict[str, object]]) -> str:
    """One line per question and the totals."""
    lines = ["id   type        expected  shown  cited  seconds  rejected"]
    for row in rows:
        reason = str(row["rejected_reason"] or row["error"])[:60]
        lines.append(
            f"{row['id']}  {row['response_type']:<11} {'ok' if row['type_ok'] else 'NO':<9} "
            f"{'yes' if row['shown_model_answer'] else '-':<6} "
            f"{ {True: 'yes', False: 'NO', None: '-'}[row['expected_cited']]:<6} "
            f"{row['seconds']:<8} {reason}"
        )
    called = [row for row in rows if row["raw_reply"]]
    shown = sum(1 for row in called if row["shown_model_answer"])
    lines.append(
        f"\n{len(rows)} questions; reply type as expected: "
        f"{sum(1 for row in rows if row['type_ok'])}; model answers shown: {shown}/{len(called)}; "
        f"average model time: "
        f"{sum(float(row['seconds']) for row in called) / max(len(called), 1):.0f}s"
    )
    return "\n".join(lines)


def main() -> None:
    """Run the test questions and print the summary."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Evaluate the configured model.")
    parser.add_argument("--only", nargs="*", help="question ids to run, e.g. Q01 Q02")
    arguments = parser.parse_args()
    cases = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))["questions"]
    if arguments.only:
        cases = [case for case in cases if case["id"] in set(arguments.only)]
    RESULTS_DIR.mkdir(exist_ok=True)
    safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "_", settings.llm_model)
    out_path = RESULTS_DIR / f"{safe_model}-{time.strftime('%Y%m%d-%H%M')}.jsonl"
    rows = run(cases, out_path)
    print("\n" + summary(rows))
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
