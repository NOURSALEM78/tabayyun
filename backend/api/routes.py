"""HTTP endpoints for both paths and the lists the interface needs.

* POST /api/ask      Path 1: a question about the regulations.
* POST /api/access   Path 2: an access request decided by the decision matrix.
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

from backend.api.schemas import (
    AccessDecisionOut,
    AccessRequestIn,
    ActionOut,
    AmendedOut,
    AskRequest,
    AskResponse,
    EmployeeOut,
    QuotedOut,
    ResourceOut,
    SourceOut,
)
from backend.db.database import SessionLocal, engine
from backend.db.models import Action, Employee, Resource, Role
from backend.llm.answer import render
from backend.llm.client import LLMError
from backend.llm.constants import UNVERIFIED_TEXT
from backend.llm.service import AnswerService
from backend.retrieval.queries import UnknownEmployeeError
from backend.services.access import AccessLookupError, decide_access
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


SessionDep = Annotated[Session, Depends(get_session)]
ServiceDep = Annotated[AnswerService, Depends(get_answer_service)]


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, service: ServiceDep) -> AskResponse:
    """Answer a question with the employee's permissions; slow on CPU (about a minute)."""
    try:
        outcome = service.ask(body.employee_id, body.question.strip())
    except UnknownEmployeeError as error:
        raise HTTPException(status_code=404, detail="الموظف غير موجود أو غير نشط") from error
    except LLMError as error:
        raise HTTPException(status_code=503, detail=f"النموذج اللغوي غير متاح: {error}") from error
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
