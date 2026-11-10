"""Request and response bodies of the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    employee_id: str = Field(examples=["E001"])
    question: str = Field(min_length=3, max_length=1000, examples=["كم مدة التبليغ عن المواليد؟"])


class SourceOut(BaseModel):
    number: int
    citation: str
    amended: bool = False


class AmendedOut(BaseModel):
    """An article marked as amended: named with a notice and referral, never its text."""

    number: int
    citation: str
    notice: str


class QuotedOut(BaseModel):
    """An article shown word for word because the model's answer failed the checks."""

    number: int
    citation: str
    text: str


class AskResponse(BaseModel):
    query_id: int | None
    response_type: str = Field(description="answer, referral or insufficient")
    answer: str = Field(description="The model's checked answer, or a fixed sentence")
    verified: bool = Field(description="False when the model's answer failed the checks")
    quoted: list[QuotedOut]
    amended: list[AmendedOut]
    referrals: list[str]
    sources: list[SourceOut]
    reply: str = Field(description="The whole reply as plain text, in reading order")
    model: str
    seconds: float


class AccessRequestIn(BaseModel):
    employee_id: str = Field(examples=["E001"])
    resource_id: str = Field(examples=["RS01"])
    action_id: str = Field(examples=["A1"])


class AccessDecisionOut(BaseModel):
    request_id: int | None
    decision: str = Field(description="allowed, denied or requires_approval")
    decision_label: str
    status: str = Field(description="auto (decided by the matrix) or pending (needs approval)")
    employee_id: str
    role_name: str
    resource_id: str
    resource_name: str
    classification: str
    action_id: str
    action_name: str
    approver: str | None
    explanation: str
    legal_basis: str
    article: str | None
    next_step: str
    rule_id: str


class EmployeeOut(BaseModel):
    employee_id: str
    name: str
    role_id: str
    role_name: str
    department: str
    access_level: int


class ResourceOut(BaseModel):
    resource_id: str
    name: str
    resource_type: str
    classification: str


class ActionOut(BaseModel):
    action_id: str
    name: str
    definition: str
