"""Запись действий пользователей в audit_log (ТЗ: security & compliance)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


async def log_action(
    db: AsyncSession,
    *,
    action: str,
    user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    changes: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """Добавляет запись аудита в текущую сессию; commit делает вызывающий код."""
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            changes=changes,
            ip_address=ip_address,
        )
    )
