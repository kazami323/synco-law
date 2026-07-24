"""Отметки («плашки») на документах: простановка, снятие, каталог.

Плашки идут параллельно статусу договора — на документе одновременно могут
висеть «Проверено ИИ», «Подготовлено» и «Утверждено», каждая со своим автором.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.contracts import get_visible_contract
from app.core.dependencies import get_current_user
from app.core.labels import (
    LABEL_CATALOGUE,
    is_auto_only,
    is_known_label,
    label_permission,
    role_title,
)
from app.core.permissions import ROLE_PERMISSIONS
from app.db.base import get_db
from app.db.models import User
from app.services.labels import describe, list_labels, remove_label, set_label
from app.utils.audit import log_action

router = APIRouter(prefix="/api", tags=["labels"])


class LabelOut(BaseModel):
    kind: str
    title: str
    tone: str
    actor_type: str
    actor_name: str | None = None
    actor_role: str | None = None
    actor_role_title: str | None = None
    by: str
    note: str | None = None
    created_at: datetime


class LabelCatalogueItem(BaseModel):
    kind: str
    title: str
    tone: str
    auto_only: bool
    can_set: bool


class SetLabelRequest(BaseModel):
    note: str | None = None


def _can_set(user: User, kind: str) -> bool:
    if is_auto_only(kind):
        return False
    needed = label_permission(kind)
    if needed is None:
        return False
    return needed in ROLE_PERMISSIONS.get(user.role, [])


def _serialize(label) -> LabelOut:
    spec = LABEL_CATALOGUE.get(label.kind, {})
    return LabelOut(
        kind=label.kind,
        title=spec.get("title", label.kind),
        tone=spec.get("tone", "neutral"),
        actor_type=label.actor_type,
        actor_name=label.actor_name,
        actor_role=label.actor_role,
        actor_role_title=role_title(label.actor_role),
        by=describe(label),
        note=label.note,
        created_at=label.created_at,
    )


@router.get("/labels/catalogue", response_model=list[LabelCatalogueItem])
async def catalogue(user: User = Depends(get_current_user)):
    """Какие плашки бывают и какие из них текущий пользователь может ставить."""
    return [
        LabelCatalogueItem(
            kind=kind,
            title=spec["title"],
            tone=spec["tone"],
            auto_only=bool(spec.get("auto_only")),
            can_set=_can_set(user, kind),
        )
        for kind, spec in LABEL_CATALOGUE.items()
    ]


@router.get("/contracts/{contract_id}/labels", response_model=list[LabelOut])
async def get_labels(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contract = await get_visible_contract(contract_id, user, db)
    return [_serialize(item) for item in await list_labels(db, contract.id)]


@router.put("/contracts/{contract_id}/labels/{kind}", response_model=LabelOut)
async def put_label(
    contract_id: uuid.UUID,
    kind: str,
    request: Request,
    data: SetLabelRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not is_known_label(kind):
        raise HTTPException(
            status_code=404,
            detail=f"Неизвестная отметка. Доступны: {sorted(LABEL_CATALOGUE)}",
        )
    if is_auto_only(kind):
        raise HTTPException(
            status_code=400,
            detail="Эта отметка ставится автоматически после проверки ИИ",
        )
    if not _can_set(user, kind):
        raise HTTPException(
            status_code=403, detail="Недостаточно прав для этой отметки"
        )

    contract = await get_visible_contract(contract_id, user, db)
    label = await set_label(
        db, contract.id, kind, user=user, note=data.note if data else None
    )
    await log_action(
        db,
        action="label_set",
        user_id=user.id,
        resource_type="contract",
        resource_id=contract.id,
        changes={"kind": kind, "note": data.note if data else None},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(label)
    return _serialize(label)


@router.delete("/contracts/{contract_id}/labels/{kind}", status_code=204)
async def delete_label(
    contract_id: uuid.UUID,
    kind: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not is_known_label(kind):
        raise HTTPException(status_code=404, detail="Неизвестная отметка")
    # Снять плашку может тот же, кто вправе её поставить; автоматическую
    # «Проверено ИИ» снимать руками нельзя — она отражает факт проверки.
    if is_auto_only(kind):
        raise HTTPException(
            status_code=400, detail="Автоматическую отметку снять нельзя"
        )
    if not _can_set(user, kind):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    contract = await get_visible_contract(contract_id, user, db)
    removed = await remove_label(db, contract.id, kind)
    if not removed:
        raise HTTPException(status_code=404, detail="Отметка не стоит")
    await log_action(
        db,
        action="label_removed",
        user_id=user.id,
        resource_type="contract",
        resource_id=contract.id,
        changes={"kind": kind},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
