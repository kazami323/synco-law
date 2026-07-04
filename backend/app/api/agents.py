"""Запуск AI-анализа и получение результатов — реализация на Weeks 7-8 (Task 1.15)."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.permissions import require_permission
from app.db.models import User

router = APIRouter(prefix="/api/contracts", tags=["ai-analysis"])


@router.post("/{contract_id}/analyze")
async def trigger_analysis(
    contract_id: str,
    user: User = Depends(require_permission("edit")),
):
    # TODO Weeks 7-8: запуск ContractAnalysisOrchestrator, сохранение AgentResult
    raise HTTPException(status_code=501, detail="Implemented in Weeks 7-8")


@router.get("/{contract_id}/analysis")
async def get_analysis(
    contract_id: str,
    user: User = Depends(require_permission("view_all")),
):
    # TODO Weeks 7-8: выборка сохранённых результатов анализа из agent_results
    raise HTTPException(status_code=501, detail="Implemented in Weeks 7-8")
