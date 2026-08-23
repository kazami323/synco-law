"""Доступ к проектам по составу участников (ТЗ, раздел 1).

Правило одно: **если у проекта назначены участники, видеть его могут только
они** — плюс роли, которым ТЗ (раздел 7) прямо даёт доступ ко всем проектам:
старший юрист, руководитель отдела, администратор. Проект без участников
остаётся общим для организации.

До появления этого модуля поле `ProjectMember.access` только хранилось:
интерфейс показывал чип «Просмотр», а на деле юрист, посаженный на дело одного
клиента, видел договоры всех остальных. Для фирмы, ведущей дела конкурирующих
контрагентов, это конфликт интересов, а продукт при этом сообщал обратное.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import has_permission
from app.db.models import Project, ProjectMember, User


async def hidden_project_ids(db: AsyncSession, user: User) -> list[uuid.UUID]:
    """Проекты организации, закрытые для пользователя составом участников.

    Пустой список означает «ничего не скрыто»: либо у роли есть доступ ко всем
    проектам, либо проектов с назначенными участниками нет.
    """
    if user.organization_id is None or has_permission(user, "view_all_projects"):
        return []

    own = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
    rows = await db.execute(
        select(ProjectMember.project_id)
        .join(Project, Project.id == ProjectMember.project_id)
        .where(
            Project.organization_id == user.organization_id,
            ProjectMember.project_id.not_in(own),
        )
        .distinct()
    )
    return list(rows.scalars().all())


async def member_access(
    db: AsyncSession, project_id: uuid.UUID, user: User
) -> str | None:
    """Уровень доступа пользователя к проекту: read | comment | write | None."""
    return (
        await db.execute(
            select(ProjectMember.access).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
