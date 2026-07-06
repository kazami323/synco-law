"""Поиск по архиву контрактов (Phase 2).

Elasticsearch с подсветкой фрагментов; при недоступном ES — прозрачный
fallback на SQL ILIKE с самодельными сниппетами.
"""

import html
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.permissions import ROLE_PERMISSIONS
from app.db.base import get_db
from app.db.models import Contract, User
from app.services import search as search_service

router = APIRouter(prefix="/api/search", tags=["search"])


def _sql_snippet(content: str | None, q: str) -> list[str]:
    """±80 символов вокруг первого совпадения, экранировано, с <mark>."""
    if not content or not q:
        return []
    match = re.search(re.escape(q), content, re.IGNORECASE)
    if not match:
        return []
    start = max(match.start() - 80, 0)
    end = min(match.end() + 80, len(content))
    prefix = html.escape(("…" if start > 0 else "") + content[start : match.start()])
    hit = html.escape(content[match.start() : match.end()])
    suffix = html.escape(content[match.end() : end] + ("…" if end < len(content) else ""))
    return [f"{prefix}<mark>{hit}</mark>{suffix}"]


async def _sql_fallback(
    db: AsyncSession,
    *,
    org_id,
    q: str | None,
    contract_type: str | None,
    status: str | None,
    risk: str | None,
    counterparty: str | None,
    date_from: date | None,
    date_to: date | None,
    created_by,
    page: int,
    size: int,
) -> dict:
    query = select(Contract).where(Contract.organization_id == org_id)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(
                Contract.title.ilike(pattern),
                Contract.content.ilike(pattern),
                Contract.counterparty.ilike(pattern),
            )
        )
    if contract_type:
        query = query.where(Contract.contract_type == contract_type)
    if status:
        query = query.where(Contract.status == status)
    if counterparty:
        query = query.where(Contract.counterparty.ilike(f"%{counterparty}%"))
    if risk == "high":
        query = query.where(Contract.risk_score > 70)
    elif risk == "medium":
        query = query.where(Contract.risk_score.between(40, 70))
    elif risk == "low":
        query = query.where(Contract.risk_score < 40)
    if date_from:
        query = query.where(func.date(Contract.created_at) >= date_from)
    if date_to:
        query = query.where(func.date(Contract.created_at) <= date_to)
    if created_by:
        query = query.where(Contract.created_by == created_by)

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                query.order_by(Contract.updated_at.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        )
        .scalars()
        .all()
    )
    return {
        "total": total,
        "items": [
            {
                "id": str(c.id),
                "title": c.title,
                "title_highlight": None,
                "snippets": _sql_snippet(c.content, q or ""),
                "counterparty": c.counterparty,
                "contract_type": c.contract_type,
                "status": c.status,
                "risk_score": c.risk_score,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in rows
        ],
        "engine": "sql",
    }


@router.get("/")
async def search_archive(
    q: str | None = None,
    contract_type: str | None = None,
    status: str | None = None,
    risk: str | None = Query(None, pattern="^(high|medium|low)$"),
    counterparty: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.organization_id is None:
        raise HTTPException(status_code=400, detail="Create an organization first")
    perms = ROLE_PERMISSIONS.get(user.role, [])
    if "view_all" not in perms and "view_assigned" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied")
    created_by = None if "view_all" in perms else user.id

    common = dict(
        org_id=user.organization_id,
        q=q,
        contract_type=contract_type,
        status=status,
        risk=risk,
        counterparty=counterparty,
        date_from=date_from,
        date_to=date_to,
        page=page,
        size=size,
    )
    try:
        return await search_service.search_contracts(
            created_by=str(created_by) if created_by else None, **common
        )
    except Exception:
        return await _sql_fallback(db, created_by=created_by, **common)
