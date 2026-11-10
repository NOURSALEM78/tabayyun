"""HTTP endpoints for both paths and the lists the interface needs.

* POST /api/ask            Path 1: a question about the regulations (waits for the answer).
* POST /api/ask/jobs       Path 1 for the interface: returns at once; poll
  GET /api/ask/jobs/{id}   until the answer is ready. Keeps the conversation.
* GET  /api/conversations, /api/conversations/{id}: the employee's chats.
* POST /api/access         Path 2: an access request decided by the decision matrix.
* GET  /api/requests       The employee's access requests.
* GET  /api/documents      Documents the employee may see.
* GET  /api/employees, /api/resources, /api/actions: choices for the interface.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.jobs import STATUS_DONE, STATUS_ERROR, JobQueue
from backend.api.schemas import (
    AccessDecisionOut,
    AccessRequestIn,
    ActionOut,
    AmendedOut,
    AskJobIn,
    AskJobOut,
    AskRequest,
    AskResponse,
    ConversationOut,
    DocumentOut,
    EmployeeOut,
    MessageOut,
    QuotedOut,
    RequestOut,
    ResourceOut,
    SourceOut,
)
from backend.db.database import SessionLocal, engine
from backend.db.models import Action, Employee, Resource, Role
from backend.llm.answer import render
from backend.llm.client import LLMError
from backend.llm.constants import UNVERIFIED_TEXT
from backend.llm.service import AnswerService, AskResult
from backend.retrieval.queries import UnknownEmployeeError
from backend.services import conversations
from backend.services.access import AccessLookupError, decide_access
from backend.services.catalog import documents_for, requests_for
from backend.services.constants import CLASSIFICATION_NAMES

router = APIRouter(prefix="/api")


def get_session() -> Iterator[Session]:
    """One database session per request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@lru_cache(maxsize=1)
def get_answer_service() -> AnswerService:
    """One answer service for the whole app, so the models load only once."""
    return AnswerService(engine)


@lru_cache(maxsize=1)
def get_jobs() -> JobQueue:
    """One background queue for the whole app."""
    return JobQueue()


def get_engine():
    """The database engine (replaced in tests)."""
    return engine


SessionDep = Annotated[Session, Depends(get_session)]
ServiceDep = Annotated[AnswerService, Depends(get_answer_service)]


EngineDep = Annotated[object, Depends(get_engine)]
JobsDep = Annotated[JobQueue, Depends(get_jobs)]
ASK_ERRORS = {UnknownEmployeeError: 404, LLMError: 503}


def to_response(outcome: AskResult) -> AskResponse:
    """The API form of an answer."""
    answer = outcome.answer
    return AskResponse(
        query_id=outcome.query_id,
        response_type=answer.response_type,
        answer=answer.text,
        verified=answer.text != UNVERIFIED_TEXT,
        quoted=[QuotedOut(number=s.number, citation=s.citation, text=s.text) for s in answer.quoted],
        amended=[AmendedOut(**asdict(item)) for item in answer.amended],
        referrals=answer.referrals,
        sources=[SourceOut(**asdict(source)) for source in answer.sources],
        reply=render(answer),
        model=outcome.model,
        seconds=outcome.seconds,
    )


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, service: ServiceDep) -> AskResponse:
    """Answer a question with the employee's permissions; slow on CPU (about a minute)."""
    try:
        outcome = service.ask(body.employee_id, body.question.strip())
    except UnknownEmployeeError as error:
        raise HTTPException(status_code=404, detail="الموظف غير موجود أو غير نشط") from error
    except LLMError as error:
        raise HTTPException(status_code=503, detail=f"النموذج اللغوي غير متاح: {error}") from error
    return to_response(outcome)


@router.post("/ask/jobs", response_model=AskJobOut, status_code=202)
def start_question(
    body: AskJobIn, service: ServiceDep, jobs: JobsDep, db_engine: EngineDep
) -> AskJobOut:
    """Start answering in the background and return the job id at once."""
    question = body.question.strip()
    try:
        conversation_id, previous = conversations.start_or_continue(
            db_engine, body.employee_id, question, body.conversation_id
        )
    except conversations.ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="المحادثة غير موجودة") from error

    def work() -> dict:
        reply = to_response(service.ask(body.employee_id, question, previous=previous))
        data = reply.model_dump(mode="json")
        conversations.add_message(db_engine, conversation_id, question, data, reply.query_id)
        return data

    job = jobs.submit(body.employee_id, conversation_id, work, ASK_ERRORS)
    return AskJobOut(job_id=job.job_id, conversation_id=conversation_id, status=job.status)


@router.get("/ask/jobs/{job_id}", response_model=AskJobOut)
def question_status(job_id: str, jobs: JobsDep) -> AskJobOut:
    """running while the answer is prepared, then done with the result (or error)."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    return AskJobOut(
        job_id=job.job_id,
        conversation_id=job.conversation_id,
        status=job.status,
        result=AskResponse(**job.result) if job.status == STATUS_DONE else None,
        error=job.error if job.status == STATUS_ERROR else "",
    )


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(employee_id: str, db_engine: EngineDep) -> list[ConversationOut]:
    """The employee's conversations, most recent first."""
    rows = conversations.list_conversations(db_engine, employee_id)
    return [ConversationOut(**row) for row in rows]


@router.get("/conversations/{conversation_id}", response_model=list[MessageOut])
def conversation(conversation_id: int, employee_id: str, db_engine: EngineDep) -> list[MessageOut]:
    """The messages of one of the employee's conversations."""
    try:
        rows = conversations.conversation_messages(db_engine, conversation_id, employee_id)
    except conversations.ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="المحادثة غير موجودة") from error
    return [MessageOut(**row) for row in rows]


@router.get("/documents", response_model=list[DocumentOut])
def documents(employee_id: str, db_engine: EngineDep) -> list[DocumentOut]:
    """Documents in force the employee may see."""
    try:
        return [DocumentOut(**row) for row in documents_for(db_engine, employee_id)]
    except UnknownEmployeeError as error:
        raise HTTPException(status_code=404, detail="الموظف غير موجود أو غير نشط") from error


@router.get("/requests", response_model=list[RequestOut])
def requests(employee_id: str, db_engine: EngineDep) -> list[RequestOut]:
    """The employee's access requests, most recent first."""
    return [RequestOut(**row) for row in requests_for(db_engine, employee_id)]


@router.post("/access", response_model=AccessDecisionOut)
def access(body: AccessRequestIn, session: SessionDep) -> AccessDecisionOut:
    """Decide an access request from the matrix and record it."""
    try:
        decision = decide_access(session, body.employee_id, body.resource_id, body.action_id)
    except AccessLookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return AccessDecisionOut(**asdict(decision))


@router.get("/employees", response_model=list[EmployeeOut])
def employees(session: SessionDep) -> list[EmployeeOut]:
    """Active employees with their role (the interface's employee picker)."""
    rows = session.execute(
        select(Employee, Role)
        .join(Role, Role.role_id == Employee.role_id)
        .where(Employee.is_active.is_(True))
        .order_by(Employee.employee_id)
    )
    return [
        EmployeeOut(
            employee_id=row.Employee.employee_id,
            name=row.Employee.name,
            role_id=row.Role.role_id,
            role_name=row.Role.name_ar,
            department=row.Employee.department,
            access_level=row.Role.access_level,
        )
        for row in rows
    ]


@router.get("/resources", response_model=list[ResourceOut])
def resources(session: SessionDep) -> list[ResourceOut]:
    """Resources that can be requested."""
    rows = session.scalars(select(Resource).order_by(Resource.resource_id))
    return [
        ResourceOut(
            resource_id=row.resource_id,
            name=row.name,
            resource_type=row.resource_type,
            classification=CLASSIFICATION_NAMES.get(row.classification_level, ""),
        )
        for row in rows
    ]


@router.get("/actions", response_model=list[ActionOut])
def actions(session: SessionDep) -> list[ActionOut]:
    """Actions that can be requested on a resource."""
    rows = session.scalars(select(Action).order_by(Action.action_id))
    return [ActionOut(action_id=r.action_id, name=r.name, definition=r.definition) for r in rows]
