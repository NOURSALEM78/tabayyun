"""Run slow questions in the background so the browser never waits on one request.

POST /api/ask/jobs returns at once with a job id; the interface then polls
GET /api/ask/jobs/{id} every few seconds. One worker answers questions in turn,
since the language model on one machine handles one request at a time. Jobs live in
memory: a server restart forgets unfinished ones (their conversations remain).
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_ERROR = "error"
MAX_KEPT_JOBS = 200


@dataclass(slots=True)
class Job:
    job_id: str
    employee_id: str
    conversation_id: int
    status: str = STATUS_RUNNING
    result: dict[str, Any] | None = None
    error: str = ""
    error_code: int = 0


@dataclass
class JobQueue:
    """Background jobs with one worker."""

    jobs: dict[str, Job] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _pool: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(max_workers=1))

    def submit(
        self,
        employee_id: str,
        conversation_id: int,
        work: Callable[[], dict[str, Any]],
        errors: dict[type[Exception], int],
    ) -> Job:
        """Start work in the background; exceptions listed in errors map to status codes."""
        job = Job(uuid.uuid4().hex, employee_id, conversation_id)
        with self._lock:
            if len(self.jobs) >= MAX_KEPT_JOBS:
                for old in [j for j in self.jobs.values() if j.status != STATUS_RUNNING][:50]:
                    self.jobs.pop(old.job_id, None)
            self.jobs[job.job_id] = job

        def run() -> None:
            try:
                job.result = work()
                job.status = STATUS_DONE
            except Exception as failure:
                code = next((c for kind, c in errors.items() if isinstance(failure, kind)), 500)
                if code == 500:
                    logger.exception("Question job failed")
                job.error, job.error_code, job.status = str(failure), code, STATUS_ERROR

        self._pool.submit(run)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)
