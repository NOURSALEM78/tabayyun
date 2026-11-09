"""Ask a question as an employee and print the full reply.

Run with ``python -m backend.llm.ask "السؤال" --employee E001``. The model is set by
LLM_BASE_URL and LLM_MODEL in .env (see README, «Answers (language model)»).
"""

from __future__ import annotations

import argparse
import logging
import time

from backend.llm.answer import compose_answer, render
from backend.llm.client import OpenAICompatibleModel
from backend.retrieval.constants import RESULTS_LIMIT
from backend.retrieval.embed import SentenceTransformerEncoder
from backend.retrieval.search import Retriever
from backend.settings import settings

logger = logging.getLogger(__name__)


def main() -> None:
    """Retrieve, compose and print one answer."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Ask the regulations a question.")
    parser.add_argument("question")
    parser.add_argument("--employee", default="E001")
    parser.add_argument("--limit", type=int, default=RESULTS_LIMIT)
    arguments = parser.parse_args()

    model = OpenAICompatibleModel(
        settings.llm_base_url, settings.llm_model, settings.llm_api_key, settings.llm_timeout
    )
    result = Retriever(SentenceTransformerEncoder()).retrieve(
        arguments.question, arguments.employee, arguments.limit
    )
    started = time.monotonic()
    answer = compose_answer(arguments.question, result, model)
    if answer.model_called:
        logger.info("%s answered in %.0fs", settings.llm_model, time.monotonic() - started)
    print("\n" + render(answer))


if __name__ == "__main__":
    main()
