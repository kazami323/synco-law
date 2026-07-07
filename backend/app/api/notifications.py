import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.base import get_db
from app.db.models import Contract, Notification, User
from app.db.schemas import NotificationOut
from app.services.email import email_enabled
from app.services.notifications import mark_notification_read
from app.services.telegram import (
    get_bot_username,
    issue_link_code,
    telegram_enabled,
)

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


@router.get("/channels")
async def notification_channels(
    user: User = Depends(get_current_user),
):
    """Состояние каналов доставки для настроек."""
    bot = await get_bot_username() if telegram_enabled() else None
    return {
        "email_enabled": email_enabled(),
        "telegram_enabled": telegram_enabled(),
        "telegram_linked": bool(user.telegram_chat_id),
        "bot_username": bot,
    }


@router.post("/telegram/link")
async def create_telegram_link(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Выдаёт одноразовый код привязки: отправьте боту /start <код>."""
    if not telegram_enabled():
        raise HTTPException(
            status_code=503,
            detail="Telegram-бот не настроен: добавьте TELEGRAM_BOT_TOKEN в backend/.env",
        )
    code = issue_link_code(user)
    await db.commit()
    bot = await get_bot_username()
    return {"code": code, "bot_username": bot}


@router.delete("/telegram/link")
async def unlink_telegram(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.telegram_chat_id = None
    user.telegram_link_code = None
    await db.commit()
    return {"detail": "unlinked"}


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
