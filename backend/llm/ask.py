"""Ask a question as an employee and print the full reply.

Run with ``python -m backend.llm.ask "السؤال" --employee E001``. The model is set by
LLM_BASE_URL and LLM_MODEL in .env (see README, «Answers (language model)»).
"""

from __future__ import annotations

import argparse
import gc
import logging
import sys
import time

from backend.llm.answer import compose_answer, render
from backend.llm.client import LLMError, OpenAICompatibleModel
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
        settings.llm_base_url,
        settings.llm_model,
        settings.llm_api_key,
        settings.llm_timeout,
        settings.llm_reasoning_effort,
    )
    retriever = Retriever(SentenceTransformerEncoder())
    result = retriever.retrieve(arguments.question, arguments.employee, arguments.limit)
    # Free the search model before the language model loads: both share the machine's memory.
    del retriever
    gc.collect()

    started = time.monotonic()
    try:
        answer = compose_answer(arguments.question, result, model)
    except LLMError as error:
        logger.error("%s", error)
        sys.exit(1)
    if answer.model_called:
        logger.info("%s answered in %.0fs", settings.llm_model, time.monotonic() - started)
    if answer.rejected_reason:
        logger.warning("Model answer not shown: %s", answer.rejected_reason)
    print("\n" + render(answer))


if __name__ == "__main__":
    main()
