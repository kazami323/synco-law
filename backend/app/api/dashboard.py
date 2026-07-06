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


@router.get("/analytics")
async def get_analytics(
    months: int = 6,
    user: User = Depends(require_permission("view_all")),
    db: AsyncSession = Depends(get_db),
):
    """CEO-аналитика (Phase 2): динамика, типы, контрагенты, риски."""
    if user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Create an organization first",
        )
    org_id = user.organization_id
    months = max(1, min(months, 24))

    # Динамика по месяцам: создано и подписано
    month_start = func.date_trunc("month", Contract.created_at)
    created_rows = (
        await db.execute(
            select(month_start.label("m"), func.count().label("n"))
            .where(Contract.organization_id == org_id)
            .group_by("m")
        )
    ).all()
    signed_month = func.date_trunc("month", Contract.signed_at)
    signed_rows = (
        await db.execute(
            select(signed_month.label("m"), func.count().label("n"))
            .where(Contract.organization_id == org_id, Contract.signed_at.isnot(None))
            .group_by("m")
        )
    ).all()
    created_by_month = {r.m.strftime("%Y-%m"): r.n for r in created_rows if r.m}
    signed_by_month = {r.m.strftime("%Y-%m"): r.n for r in signed_rows if r.m}

    today = date.today().replace(day=1)
    series = []
    for offset in range(months - 1, -1, -1):
        year = today.year + (today.month - 1 - offset) // 12
        month = (today.month - 1 - offset) % 12 + 1
        key = f"{year:04d}-{month:02d}"
        series.append(
            {
                "month": key,
                "created": created_by_month.get(key, 0),
                "signed": signed_by_month.get(key, 0),
            }
        )

    # Распаковка позиционно: метка вроде "t" конфликтует с Row.t (SQLAlchemy)
    by_type = [
        {"type": ctype or "other", "count": count}
        for ctype, count in (
            await db.execute(
                select(Contract.contract_type, func.count())
                .where(Contract.organization_id == org_id)
                .group_by(Contract.contract_type)
                .order_by(func.count().desc())
            )
        ).all()
    ]

    top_counterparties = [
        {
            "counterparty": counterparty,
            "total_amount": float(total or 0),
            "count": count,
        }
        for counterparty, total, count in (
            await db.execute(
                select(
                    Contract.counterparty,
                    func.sum(Contract.amount),
                    func.count(),
                )
                .where(
                    Contract.organization_id == org_id,
                    Contract.counterparty.isnot(None),
                )
                .group_by(Contract.counterparty)
                .order_by(func.sum(Contract.amount).desc().nulls_last())
                .limit(5)
            )
        ).all()
    ]

    risk_row = (
        await db.execute(
            select(
                func.count().filter(Contract.risk_score > 70).label("high"),
                func.count()
                .filter(Contract.risk_score.between(40, 70))
                .label("medium"),
                func.count()
                .filter(Contract.risk_score < 40, Contract.risk_score.isnot(None))
                .label("low"),
                func.count().filter(Contract.risk_score.is_(None)).label("unscored"),
            ).where(Contract.organization_id == org_id)
        )
    ).one()

    totals_row = (
        await db.execute(
            select(
                func.count().label("contracts"),
                func.sum(Contract.amount)
                .filter(Contract.status == "signed")
                .label("signed_amount"),
                func.avg(Contract.risk_score).label("avg_risk"),
                func.count()
                .filter(Contract.status.notin_(["archived", "signed"]))
                .label("in_work"),
            ).where(Contract.organization_id == org_id)
        )
    ).one()

    return {
        "months": series,
        "by_type": by_type,
        "top_counterparties": top_counterparties,
        "risk": {
            "high": risk_row.high,
            "medium": risk_row.medium,
            "low": risk_row.low,
            "unscored": risk_row.unscored,
        },
        "totals": {
            "contracts": totals_row.contracts,
            "signed_amount": float(totals_row.signed_amount or 0),
            "avg_risk": round(totals_row.avg_risk, 1)
            if totals_row.avg_risk is not None
            else None,
            "in_work": totals_row.in_work,
        },
    }
