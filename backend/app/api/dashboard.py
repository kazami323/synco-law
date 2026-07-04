"""Метрики дашборда руководителя (Task 1.14) — реальные данные из БД."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.db.base import get_db
from app.db.models import Contract, ContractDeadline, User
from app.services.deadlines import days_left

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/metrics")
async def get_dashboard_metrics(
    user: User = Depends(require_permission("view_all")),
    db: AsyncSession = Depends(get_db),
):
    if user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Create an organization first",
        )

    row = (
        await db.execute(
            select(
                func.count().filter(Contract.status != "draft").label("reviewed"),
                func.count().filter(Contract.risk_score > 70).label("high"),
                func.count()
                .filter(Contract.risk_score.between(40, 70))
                .label("medium"),
                func.count()
                .filter(Contract.risk_score < 40, Contract.risk_score.isnot(None))
                .label("low"),
                func.count()
                .filter(
                    Contract.status.in_(
                        [
                            "analyzing",
                            "analyzed",
                            "approved",
                            "approved_finance",
                            "ready_to_sign",
                        ]
                    )
                )
                .label("pending"),
                func.count().filter(Contract.status == "signed").label("signed"),
            ).where(Contract.organization_id == user.organization_id)
        )
    ).one()

    today = date.today()
    window_end = today + timedelta(days=7)
    upcoming_count = (
        await db.execute(
            select(func.count(func.distinct(ContractDeadline.contract_id)))
            .join(Contract, ContractDeadline.contract_id == Contract.id)
            .where(
                Contract.organization_id == user.organization_id,
                Contract.status != "archived",
                ContractDeadline.deadline_date <= window_end,
            )
        )
    ).scalar_one()
    upcoming_rows = (
        await db.execute(
            select(ContractDeadline, Contract)
            .join(Contract, ContractDeadline.contract_id == Contract.id)
            .where(
                Contract.organization_id == user.organization_id,
                Contract.status != "archived",
                ContractDeadline.deadline_date <= window_end,
            )
            .order_by(ContractDeadline.deadline_date)
            .limit(5)
        )
    ).all()

    return {
        "total_reviewed": row.reviewed,
        "high_risk": row.high,
        "medium_risk": row.medium,
        "low_risk": row.low,
        "pending_approval": row.pending,
        "signed": row.signed,
        "upcoming_deadlines_count": upcoming_count,
        "upcoming_deadlines": [
            {
                "id": str(deadline.id),
                "contract_id": str(contract.id),
                "contract_title": contract.title,
                "deadline_date": deadline.deadline_date,
                "type": deadline.deadline_type,
                "days_left": days_left(deadline.deadline_date, today),
            }
            for deadline, contract in upcoming_rows
        ],
        "avg_review_time": None,  # появится вместе с workflow (Weeks 11-12)
        "hours_saved": row.reviewed * 2,  # оценка из ТЗ: ~2 часа на проверку
    }
