"""Журнал действий по документу (ТЗ, раздел 5).

Записи в `audit_log` писались с самого начала, но прочитать их было нечем:
эндпоинта не было. А ТЗ требует, чтобы каждое решение юриста фиксировалось
«с указанием автора и времени» и это можно было увидеть.

Журнал доступен тому, кто видит сам документ: доступ проверяется через
`get_visible_contract`, поэтому фильтр по организации и по участникам проекта
работает и здесь.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.contracts import get_visible_contract
from app.core.dependencies import get_current_user
from app.core.labels import role_title
from app.db.base import get_db
from app.db.models import AuditLog, User

router = APIRouter(prefix="/api", tags=["audit"])

# Действия журнала по-русски. Незнакомое действие показывается как есть —
# лучше техническое имя, чем пропущенная строка в журнале.
ACTION_TITLES: dict[str, str] = {
    "contract_created": "Документ создан",
    "contract_updated": "Документ изменён",
    "contract_archived": "Документ отправлен в архив",
    "contract_duplicated": "Создана копия документа",
    "contract_exported": "Документ выгружен",
    "contract_version_restored": "Откат к прежней версии",
    "clauses_rebuilt": "Документ заново разобран на пункты",
    "clause_decision": "Решение по пункту",
    "logic_finding_resolved": "Решение по расхождению в логике",
    "risk_finding_resolved": "Решение по риску",
    "comment_added": "Комментарий",
    "review_started": "Запущена проверка",
    "label_set": "Поставлена отметка",
    "label_removed": "Снята отметка",
    "sign_request_created": "Запрошено подписание",
    "sign_confirmed": "Документ подписан",
    "deadline_created": "Добавлен срок",
    "workflow_transition": "Смена статуса",
}

# Как назвать решение юриста по пункту — то же, что в интерфейсе проверки.
CLAUSE_ACTION_TITLES: dict[str, str] = {
    "confirm": "подтверждён",
    "edit": "изменён",
    "comment": "комментарий",
    "defer": "отложен",
}


class AuditEntryOut(BaseModel):
    id: uuid.UUID
    action: str
    title: str
    detail: str | None = None
    author_name: str | None = None
    author_role: str | None = None
    author_role_title: str | None = None
    created_at: datetime


class AuditPageOut(BaseModel):
    items: list[AuditEntryOut]
    total: int


def _detail(action: str, changes: dict | None) -> str | None:
    """Короткая суть записи. Текст документа сюда не попадает намеренно."""
    if not changes:
        return None
    if action == "clause_decision":
        anchor = changes.get("anchor")
        verb = CLAUSE_ACTION_TITLES.get(changes.get("action", ""), changes.get("action"))
        return f"Пункт {anchor}: {verb}" if anchor else verb
    if action == "review_started":
        modules = changes.get("modules") or []
        return "Модули: " + ", ".join(modules) if modules else None
    if action in {"label_set", "label_removed"}:
        return changes.get("kind")
    if action in {"logic_finding_resolved", "risk_finding_resolved"}:
        return changes.get("status")
    if action == "comment_added":
        anchor = changes.get("clause_anchor")
        return f"к пункту {anchor}" if anchor else "к документу"
    if action == "contract_updated":
        fields = [key for key in changes if key != "contract_id"]
        return "Изменено: " + ", ".join(fields) if fields else None
    if action == "contract_exported":
        parts = [str(changes[key]) for key in ("format", "mode") if changes.get(key)]
        return " / ".join(parts) or None
    return None


@router.get("/contracts/{contract_id}/audit", response_model=AuditPageOut)
async def contract_audit(
    contract_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Кто и когда что делал с документом."""
    contract = await get_visible_contract(contract_id, user, db)

    # Часть записей висит на самом документе, часть — на его пункте или
    # находке, и тогда id документа лежит в changes.
    belongs = or_(
        AuditLog.resource_id == contract.id,
        AuditLog.changes["contract_id"].astext == str(contract.id),
    )

    total = (
        await db.execute(select(func.count(AuditLog.id)).where(belongs))
    ).scalar_one()

    rows = (
        await db.execute(
            select(AuditLog, User)
            .outerjoin(User, User.id == AuditLog.user_id)
            .where(belongs)
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return AuditPageOut(
        total=total,
        items=[
            AuditEntryOut(
                id=entry.id,
                action=entry.action,
                title=ACTION_TITLES.get(entry.action, entry.action),
                detail=_detail(entry.action, entry.changes),
                author_name=(author.full_name or author.username) if author else None,
                author_role=author.role if author else None,
                author_role_title=role_title(author.role) if author else None,
                created_at=entry.created_at,
            )
            for entry, author in rows
        ],
    )
