import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.base import get_db
from app.db.models import Contract, Notification, User
from app.db.schemas import NotificationOut
from app.services.notifications import mark_notification_read

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/", response_model=list[NotificationOut])
async def list_notifications(
    limit: int = 50,
    unread_only: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Notification, Contract.title)
        .outerjoin(Contract, Notification.contract_id == Contract.id)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        query = query.where(Notification.read_at.is_(None))

    rows = (await db.execute(query)).all()
    return [
        NotificationOut(
            id=notification.id,
            user_id=notification.user_id,
            contract_id=notification.contract_id,
            text=notification.text,
            read_at=notification.read_at,
            created_at=notification.created_at,
            contract_title=contract_title,
        )
        for notification, contract_title in rows
    ]


@router.post("/read-all")
async def read_all_notifications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отметить все уведомления пользователя прочитанными."""
    result = await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=func.now())
    )
    await db.commit()
    return {"marked": result.rowcount}


@router.get("/unread-count")
async def unread_count(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        )
    ).scalar_one()
    return {"count": count}


@router.patch("/{notification_id}/read", response_model=NotificationOut)
async def read_notification(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(Notification, Contract.title)
            .outerjoin(Contract, Notification.contract_id == Contract.id)
            .where(Notification.id == notification_id, Notification.user_id == user.id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification, contract_title = row
    await mark_notification_read(notification)
    await db.commit()
    await db.refresh(notification)
    return NotificationOut(
        id=notification.id,
        user_id=notification.user_id,
        contract_id=notification.contract_id,
        text=notification.text,
        read_at=notification.read_at,
        created_at=notification.created_at,
        contract_title=contract_title,
    )
