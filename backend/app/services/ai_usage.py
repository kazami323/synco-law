"""Organization quotas and auditable Anthropic token usage."""

from __future__ import annotations

from datetime import datetime, time, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AIUsageLog, User
from app.services.rate_limit import enforce_ai_limits
from app.utils.llm import UsageCollector


async def enforce_ai_access(db: AsyncSession, user: User) -> None:
    if user.organization_id is None:
        raise HTTPException(status_code=400, detail="Create an organization first")
    await enforce_ai_limits(
        user_id=str(user.id),
        organization_id=str(user.organization_id),
    )
    day_start = datetime.combine(datetime.now(timezone.utc).date(), time.min, timezone.utc)
    used = (
        await db.execute(
            select(
                func.coalesce(
                    func.sum(AIUsageLog.input_tokens + AIUsageLog.output_tokens), 0
                )
            ).where(
                AIUsageLog.organization_id == user.organization_id,
                AIUsageLog.created_at >= day_start,
            )
        )
    ).scalar_one()
    if int(used) >= settings.AI_DAILY_TOKENS_PER_ORG:
        raise HTTPException(
            status_code=429,
            detail="Дневной лимит AI-токенов организации исчерпан",
            headers={"Retry-After": "3600"},
        )


def record_ai_usage(
    db: AsyncSession,
    user: User,
    usage: UsageCollector,
    *,
    endpoint: str,
    agent: str | None = None,
) -> None:
    if user.organization_id is None:
        return
    db.add(
        AIUsageLog(
            organization_id=user.organization_id,
            user_id=user.id,
            endpoint=endpoint,
            agent=agent,
            model=settings.ANTHROPIC_MODEL,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
    )
