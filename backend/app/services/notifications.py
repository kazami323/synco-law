from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import ROLE_PERMISSIONS
from app.db.models import Contract, ContractDeadline, Notification, User
from app.services.deadlines import days_left


def _notification_text(contract: Contract, deadline: ContractDeadline, today: date) -> str:
    left = days_left(deadline.deadline_date, today)
    if left < 0:
        prefix = f"Просрочен срок: {abs(left)} дн. назад"
    elif left == 0:
        prefix = "Срок наступает сегодня"
    else:
        prefix = f"Срок через {left} дн."
    return (
        f"{prefix}: {contract.title} "
        f"({deadline.deadline_type}, {deadline.deadline_date.isoformat()})"
    )


def _can_receive_deadline_notification(user: User, contract: Contract) -> bool:
    permissions = ROLE_PERMISSIONS.get(user.role, [])
    return "view_all" in permissions or contract.created_by == user.id


async def create_deadline_notifications(
    db: AsyncSession,
    *,
    organization_id=None,
    today: date | None = None,
) -> int:
    current = today or date.today()
    window_end = current + timedelta(days=7)
    query = (
        select(ContractDeadline, Contract)
        .join(Contract, ContractDeadline.contract_id == Contract.id)
        .where(
            ContractDeadline.deadline_date <= window_end,
            ContractDeadline.is_notified.is_(False),
            Contract.status != "archived",
        )
        .order_by(ContractDeadline.deadline_date)
    )
    if organization_id is not None:
        query = query.where(Contract.organization_id == organization_id)

    rows = (await db.execute(query)).all()
    created = 0
    for deadline, contract in rows:
        users = (
            await db.execute(
                select(User).where(
                    User.organization_id == contract.organization_id,
                    User.is_active.is_(True),
                )
            )
        ).scalars().all()
        text = _notification_text(contract, deadline, current)
        for recipient in users:
            if not _can_receive_deadline_notification(recipient, contract):
                continue
            duplicate = (
                await db.execute(
                    select(Notification.id).where(
                        Notification.user_id == recipient.id,
                        Notification.contract_id == contract.id,
                        Notification.text == text,
                    )
                )
            ).scalar_one_or_none()
            if duplicate is not None:
                continue
            db.add(
                Notification(
                    user_id=recipient.id,
                    contract_id=contract.id,
                    text=text,
                )
            )
            created += 1
        deadline.is_notified = True
    return created


async def mark_notification_read(notification: Notification) -> None:
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
