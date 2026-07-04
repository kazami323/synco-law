"""Метрики дашборда руководителя — реализация на Weeks 9-10 (Task 1.14)."""

from fastapi import APIRouter, Depends

from app.core.permissions import require_permission
from app.db.models import User

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/metrics")
async def get_dashboard_metrics(user: User = Depends(require_permission("view_all"))):
    # TODO Weeks 9-10: реальные KPI из БД
    return {
        "total_reviewed": 0,
        "high_risk": 0,
        "medium_risk": 0,
        "low_risk": 0,
        "pending_approval": 0,
        "signed": 0,
        "avg_review_time": None,
        "hours_saved": 0,
    }
