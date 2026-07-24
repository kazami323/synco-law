"""Простановка и снятие отметок («плашек») на документах.

Общий слой для ручной простановки из API и автоматической — после того как
документ прошёл через ИИ-агентов.
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.labels import agent_title, role_title
from app.db.models import DocumentLabel, User


async def list_labels(db: AsyncSession, contract_id: uuid.UUID) -> list[DocumentLabel]:
    result = await db.execute(
        select(DocumentLabel)
        .where(DocumentLabel.contract_id == contract_id)
        .order_by(DocumentLabel.created_at)
    )
    return list(result.scalars().all())


async def set_label(
    db: AsyncSession,
    contract_id: uuid.UUID,
    kind: str,
    *,
    user: User | None = None,
    agent_name: str | None = None,
    note: str | None = None,
) -> DocumentLabel:
    """Ставит отметку. Повторная простановка обновляет автора и время.

    Не коммитит — вызывающий решает, когда фиксировать транзакцию.
    """
    existing = await db.execute(
        select(DocumentLabel).where(
            DocumentLabel.contract_id == contract_id, DocumentLabel.kind == kind
        )
    )
    label = existing.scalar_one_or_none()
    if label is None:
        label = DocumentLabel(contract_id=contract_id, kind=kind)
        db.add(label)

    if user is not None:
        label.actor_type = "user"
        label.actor_user_id = user.id
        # Снимок роли и имени: если человеку позже сменят должность, старая
        # плашка не должна менять надпись задним числом.
        label.actor_role = user.role
        label.actor_name = getattr(user, "full_name", None) or user.email
        label.actor_agent = None
    else:
        label.actor_type = "agent"
        label.actor_agent = agent_name
        label.actor_name = agent_title(agent_name)
        label.actor_user_id = None
        label.actor_role = None

    label.note = note
    await db.flush()
    return label


async def remove_label(db: AsyncSession, contract_id: uuid.UUID, kind: str) -> bool:
    """Снимает отметку. Возвращает True, если она действительно стояла."""
    result = await db.execute(
        delete(DocumentLabel).where(
            DocumentLabel.contract_id == contract_id, DocumentLabel.kind == kind
        )
    )
    return bool(result.rowcount)


def describe(label: DocumentLabel) -> str:
    """Человеческая подпись под плашкой: кто поставил."""
    if label.actor_type == "agent":
        return agent_title(label.actor_agent) or "ИИ-агент"
    title = role_title(label.actor_role)
    name = label.actor_name or "пользователь"
    return f"{name} ({title})" if title else name
