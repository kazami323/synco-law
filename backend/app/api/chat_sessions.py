"""Persistent per-user AI chat sessions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.agents.chat import AGENT_PROMPTS
from app.api.contracts import get_visible_contract
from app.core.dependencies import get_current_user
from app.db.base import get_db
from app.db.models import AgentChatSession, User

router = APIRouter(prefix="/api/agents/sessions", tags=["ai-chat-sessions"])


class StoredMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=20_000)
    agent: str | None = Field(default=None, max_length=64)
    feedback: Literal["up", "down"] | None = None
    sources: list[dict] = Field(default_factory=list, max_length=10)


class MessageFeedback(BaseModel):
    rating: Literal["up", "down"] | None = None


class SessionCreate(BaseModel):
    id: uuid.UUID | None = None
    agent: str = "law"
    title: str = Field(default="Новый чат", min_length=1, max_length=256)
    messages: list[StoredMessage] = Field(default_factory=list, max_length=100)
    contract_id: uuid.UUID | None = None
    document_name: str | None = Field(default=None, max_length=512)


class SessionUpdate(BaseModel):
    agent: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=256)
    messages: list[StoredMessage] | None = Field(default=None, max_length=100)
    contract_id: uuid.UUID | None = None
    document_name: str | None = Field(default=None, max_length=512)


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent: str
    title: str
    messages: list[dict]
    contract_id: uuid.UUID | None = None
    document_name: str | None = None
    created_at: datetime
    updated_at: datetime


def _org_id(user: User) -> uuid.UUID:
    if user.organization_id is None:
        raise HTTPException(status_code=400, detail="Create an organization first")
    return user.organization_id


async def _owned_session(
    session_id: uuid.UUID, user: User, db: AsyncSession, *, lock: bool = False
) -> AgentChatSession:
    query = select(AgentChatSession).where(
        AgentChatSession.id == session_id,
        AgentChatSession.user_id == user.id,
        AgentChatSession.organization_id == _org_id(user),
    )
    if lock:
        query = query.with_for_update()
    session = (await db.execute(query)).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


def _validate_agent(agent: str) -> None:
    if agent not in AGENT_PROMPTS:
        raise HTTPException(status_code=400, detail="Unknown agent")


@router.get("/", response_model=list[SessionOut])
async def list_sessions(
    limit: int = Query(60, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(AgentChatSession)
            .where(
                AgentChatSession.user_id == user.id,
                AgentChatSession.organization_id == _org_id(user),
            )
            .order_by(AgentChatSession.updated_at.desc())
            .limit(limit)
        )
    ).scalars()
    return list(rows)


@router.post("/", response_model=SessionOut, status_code=201)
async def create_session(
    data: SessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_agent(data.agent)
    if data.contract_id:
        await get_visible_contract(data.contract_id, user, db)
    if data.id:
        existing = await db.get(AgentChatSession, data.id)
        if existing is not None:
            if existing.user_id != user.id:
                raise HTTPException(status_code=409, detail="Chat session ID already exists")
            return existing
    session = AgentChatSession(
        id=data.id or uuid.uuid4(),
        organization_id=_org_id(user),
        user_id=user.id,
        agent=data.agent,
        title=data.title,
        messages=[message.model_dump(exclude_none=True) for message in data.messages],
        contract_id=data.contract_id,
        document_name=data.document_name,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.patch("/{session_id}", response_model=SessionOut)
async def update_session(
    session_id: uuid.UUID,
    data: SessionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(session_id, user, db, lock=True)
    values = data.model_dump(exclude_unset=True)
    if "agent" in values:
        _validate_agent(values["agent"])
    if values.get("contract_id"):
        await get_visible_contract(values["contract_id"], user, db)
    if "messages" in values:
        values["messages"] = [
            message.model_dump(exclude_none=True) for message in data.messages or []
        ]
    if values.get("contract_id"):
        values["document_name"] = None
        session.document_text = None
    elif "document_name" in values and values["document_name"] is None:
        session.document_text = None
    for field, value in values.items():
        setattr(session, field, value)
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)
    return session


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(session_id, user, db, lock=True)
    await db.delete(session)
    await db.commit()


@router.put("/{session_id}/messages/{message_index}/feedback", status_code=204)
async def set_message_feedback(
    session_id: uuid.UUID,
    message_index: int,
    data: MessageFeedback,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(session_id, user, db, lock=True)
    messages = [dict(message) for message in session.messages]
    if message_index < 0 or message_index >= len(messages):
        raise HTTPException(status_code=404, detail="Message not found")
    if messages[message_index].get("role") != "assistant":
        raise HTTPException(status_code=400, detail="Only assistant messages can be rated")
    if data.rating is None:
        messages[message_index].pop("feedback", None)
    else:
        messages[message_index]["feedback"] = data.rating
    session.messages = messages
    flag_modified(session, "messages")
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()
