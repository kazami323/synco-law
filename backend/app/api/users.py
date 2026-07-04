"""Управление пользователями — реализация на Weeks 3-4."""

from fastapi import APIRouter, Depends

from app.core.permissions import require_permission
from app.db.models import User
from app.db.schemas import UserOut

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/", response_model=list[UserOut])
async def list_users(user: User = Depends(require_permission("view_all"))):
    # TODO Weeks 3-4: список пользователей организации с пагинацией
    return []
