"""Path 1 as a service: answer one question for one employee and log it.

The search model and the language model client are created on first use and kept for
later questions, so only the first request pays the loading time.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from sqlalchemy import Engine, insert

from backend.db.models import QueryLog
from backend.llm.answer import Answer, compose_answer
from backend.llm.client import ChatModel, OpenAICompatibleModel
from backend.retrieval.constants import RESULTS_LIMIT
from backend.retrieval.types import RetrievalResult

logger = logging.getLogger(__name__)

INTENT_QUESTION = "question"


@dataclass(frozen=True, slots=True)
class AskResult:
    """An answer with what produced it."""

    answer: Answer
    result: RetrievalResult
    model: str
    seconds: float
    query_id: int | None


def cited_chunk_ids(answer: Answer, result: RetrievalResult) -> list[str]:
    """Chunk ids of the articles in the answer's source list."""
    numbered = dict(enumerate((chunk.chunk_id for chunk in result.chunks), start=1))
    return [numbered[source.number] for source in answer.sources if source.number in numbered]


class AnswerService:
    """Retrieval, answer composition and query logging for the API."""

    def __init__(self, engine: Engine, retriever=None, model: ChatModel | None = None,
                 model_name: str = "") -> None:
        self._engine = engine
        self._retriever = retriever
        self._model = model
        self._model_name = model_name
        self._lock = threading.Lock()

    def _ready(self):
        """Create the retriever and model client on first use."""
        with self._lock:
            if self._retriever is None:
                from backend.retrieval.embed import SentenceTransformerEncoder
                from backend.retrieval.search import Retriever

                self._retriever = Retriever(SentenceTransformerEncoder(), self._engine)
            if self._model is None:
                from backend.settings import settings

                self._model = OpenAICompatibleModel(
                    settings.llm_base_url,
                    settings.llm_model,
                    settings.llm_api_key,
                    settings.llm_timeout,
                    settings.llm_reasoning_effort,
                )
                self._model_name = settings.llm_model
        return self._retriever, self._model

    def ask(self, employee_id: str, question: str, log: bool = True) -> AskResult:
        """Answer one question; raises UnknownEmployeeError or LLMError."""
        retriever, model = self._ready()
        started = time.monotonic()
        result = retriever.retrieve(question, employee_id, RESULTS_LIMIT)
        answer = compose_answer(question, result, model)
        seconds = round(time.monotonic() - started, 1)
        query_id = self._log(employee_id, question, answer, result) if log else None
        if answer.rejected_reason:
            logger.warning("Model answer not shown: %s", answer.rejected_reason)
        return AskResult(answer, result, self._model_name, seconds, query_id)

    def _log(self, employee_id: str, question: str, answer: Answer, result: RetrievalResult) -> int:
        """Store the question, its retrieved and cited chunks and the reply type."""
        with self._engine.begin() as connection:
            return connection.execute(
                insert(QueryLog)
                .values(
                    employee_id=employee_id,
                    question=question,
                    intent=INTENT_QUESTION,
                    retrieved_chunk_ids=[chunk.chunk_id for chunk in result.chunks],
                    cited_chunk_ids=cited_chunk_ids(answer, result),
                    response_type=answer.response_type,
                )
                .returning(QueryLog.query_id)
            ).scalar_one()
