"""CRUD контрактов — полная реализация на Weeks 5-6 (Task 1.8)."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.permissions import require_permission
from app.db.models import User
from app.db.schemas import ContractCreate

router = APIRouter(prefix="/api/contracts", tags=["contracts"])


@router.get("/")
async def list_contracts(
    page: int = 1,
    limit: int = 10,
    status_filter: str | None = None,
    user: User = Depends(require_permission("view_all")),
):
    # TODO Weeks 5-6: выборка контрактов организации с пагинацией и фильтром по статусу
    return {"total": 0, "page": page, "items": []}


@router.post("/", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def create_contract(
    data: ContractCreate,
    user: User = Depends(require_permission("create")),
):
    # TODO Weeks 5-6: создание контракта + первая версия + загрузка файла в MinIO
    raise HTTPException(status_code=501, detail="Implemented in Weeks 5-6")
