"""Store chat conversations and their messages for the interface."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, func, insert, select, update

from backend.db.models import Conversation, Message

TITLE_LENGTH = 60


class ConversationNotFoundError(LookupError):
    """Raised when a conversation does not exist or belongs to another employee."""


def _owned(connection, conversation_id: int, employee_id: str) -> None:
    owner = connection.scalar(
        select(Conversation.employee_id).where(Conversation.conversation_id == conversation_id)
    )
    if owner != employee_id:
        raise ConversationNotFoundError(f"No conversation {conversation_id} for {employee_id}")


def start_or_continue(
    engine: Engine, employee_id: str, question: str, conversation_id: int | None
) -> tuple[int, str]:
    """Return the conversation id (a new one when none is given) and its last question."""
    with engine.begin() as connection:
        if conversation_id is None:
            new_id = connection.execute(
                insert(Conversation)
                .values(employee_id=employee_id, title=question[:TITLE_LENGTH])
                .returning(Conversation.conversation_id)
            ).scalar_one()
            return new_id, ""
        _owned(connection, conversation_id, employee_id)
        previous = connection.scalar(
            select(Message.question)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.message_id.desc())
            .limit(1)
        )
        return conversation_id, previous or ""


def add_message(
    engine: Engine, conversation_id: int, question: str, reply: dict[str, Any], query_id: int | None
) -> int:
    """Store one question with the reply shown for it."""
    with engine.begin() as connection:
        message_id = connection.execute(
            insert(Message)
            .values(
                conversation_id=conversation_id, question=question, reply=reply, query_id=query_id
            )
            .returning(Message.message_id)
        ).scalar_one()
        connection.execute(
            update(Conversation)
            .where(Conversation.conversation_id == conversation_id)
            .values(updated_at=func.now())
        )
        return message_id


def list_conversations(engine: Engine, employee_id: str) -> list[dict[str, Any]]:
    """The employee's conversations, most recent first."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(Conversation.conversation_id, Conversation.title, Conversation.updated_at)
            .where(Conversation.employee_id == employee_id)
            .order_by(Conversation.updated_at.desc(), Conversation.conversation_id.desc())
        )
        return [dict(row._mapping) for row in rows]


def conversation_messages(
    engine: Engine, conversation_id: int, employee_id: str
) -> list[dict[str, Any]]:
    """The messages of one of the employee's conversations, oldest first."""
    with engine.connect() as connection:
        _owned(connection, conversation_id, employee_id)
        rows = connection.execute(
            select(Message.message_id, Message.question, Message.reply, Message.created_at)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.message_id)
        )
        return [dict(row._mapping) for row in rows]
