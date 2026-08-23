"""База шаблонов документов (ТЗ, раздел 6).

Шаблон — не просто текст: юрист берёт его в работу, полагаясь на отметку
«верифицирован». Поэтому отметка привязана к конкретному юристу и дате, а при
изменении законодательства снимается автоматически: устаревший шаблон,
выглядящий проверенным, опаснее отсутствия шаблона.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentTemplate, Notification, User


async def list_templates(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    doc_type: str | None = None,
    include_archived: bool = False,
) -> list[DocumentTemplate]:
    query = select(DocumentTemplate).where(
        DocumentTemplate.organization_id == organization_id
    )
    if doc_type:
        query = query.where(DocumentTemplate.doc_type == doc_type)
    if not include_archived:
        query = query.where(DocumentTemplate.is_archived.is_(False))
    result = await db.execute(query.order_by(DocumentTemplate.created_at.desc()))
    return list(result.scalars().all())


async def get_template(
    db: AsyncSession, template_id: uuid.UUID, organization_id: uuid.UUID
) -> DocumentTemplate | None:
    return (
        await db.execute(
            select(DocumentTemplate).where(
                DocumentTemplate.id == template_id,
                DocumentTemplate.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()


def verify(template: DocumentTemplate, user: User) -> None:
    """Отметка «верифицирован» с указанием юриста и даты (ТЗ, раздел 6)."""
    now = datetime.now(timezone.utc)
    template.verified_by = user.id
    template.verified_by_name = user.full_name or user.username
    template.verified_at = now
    template.actualized_at = now.date()
    template.stale_reason = None
    template.stale_since = None


def unverify(template: DocumentTemplate) -> None:
    template.verified_by = None
    template.verified_by_name = None
    template.verified_at = None


async def mark_templates_stale(
    db: AsyncSession, changed_acts: list[str]
) -> list[DocumentTemplate]:
    """Снимает верификацию с шаблонов после изменения законодательства.

    Сопоставить конкретный шаблон с конкретной статьёй надёжно нельзя, поэтому
    помечаются все верифицированные шаблоны. Ложное «перепроверьте» стоит
    юристу десяти минут, пропущенное изменение закона — недействительного
    условия в договоре.
    """
    if not changed_acts:
        return []

    templates = (
        (
            await db.execute(
                select(DocumentTemplate).where(
                    DocumentTemplate.is_archived.is_(False),
                    DocumentTemplate.verified_at.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not templates:
        return []

    reason = "Изменилось законодательство: " + "; ".join(sorted(set(changed_acts))[:5])
    now = datetime.now(timezone.utc)
    for template in templates:
        template.stale_reason = reason
        template.stale_since = now
        unverify(template)
        if template.created_by:
            db.add(
                Notification(
                    user_id=template.created_by,
                    text=(
                        f"Шаблон «{template.name}» требует перепроверки: {reason}"
                    )[:1024],
                )
            )
    await db.flush()
    return list(templates)
