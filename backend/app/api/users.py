"""Управление пользователями организации (Weeks 3-4, Task 1.5-1.7).

Список сотрудников — право view_all; создание/смена роли/деактивация —
право manage_users (admin, head). Все операции ограничены своей организацией.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import hash_password, validate_password
from app.db.base import get_db
from app.db.models import Role, User
from app.db.schemas import UserOut
from app.utils.audit import log_action

router = APIRouter(prefix="/api/users", tags=["users"])

VALID_ROLES = {r.value for r in Role}


class UserCreateRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=2, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128)
    full_name: str | None = Field(default=None, max_length=256)
    role: str = Role.LAWYER.value


class UserUpdateRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    full_name: str | None = None


class UserListResponse(BaseModel):
    total: int
    page: int
    items: list[UserOut]


def _require_org(user: User) -> uuid.UUID:
    if user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Create an organization first",
        )
    return user.organization_id


def _validate_role(role: str, acting_user: User) -> None:
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Allowed: {sorted(VALID_ROLES)}",
        )
    # Назначать админа может только админ
    if role == Role.ADMIN.value and acting_user.role != Role.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin can assign the admin role",
        )


@router.get("/", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_permission("view_all")),
    db: AsyncSession = Depends(get_db),
):
    """Сотрудники моей организации с пагинацией."""
    org_id = _require_org(user)

    base_query = select(User).where(User.organization_id == org_id)
    total = (
        await db.execute(
            select(func.count()).select_from(base_query.subquery())
        )
    ).scalar_one()
    result = await db.execute(
        base_query.order_by(User.created_at).offset((page - 1) * limit).limit(limit)
    )
    return UserListResponse(
        total=total, page=page, items=list(result.scalars().all())
    )


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreateRequest,
    request: Request,
    user: User = Depends(require_permission("manage_users")),
    db: AsyncSession = Depends(get_db),
):
    """Создать сотрудника в своей организации."""
    org_id = _require_org(user)
    _validate_role(data.role, user)
    try:
        validate_password(data.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = await db.execute(
        select(User).where(
            (User.email == data.email) | (User.username == data.username)
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email or username already exists",
        )

    new_user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
        organization_id=org_id,
    )
    db.add(new_user)
    await db.flush()

    await log_action(
        db,
        action="user_created",
        user_id=user.id,
        resource_type="user",
        resource_id=new_user.id,
        changes={"email": data.email, "role": data.role},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdateRequest,
    request: Request,
    user: User = Depends(require_permission("manage_users")),
    db: AsyncSession = Depends(get_db),
):
    """Смена роли, активация/деактивация, ФИО сотрудника своей организации."""
    org_id = _require_org(user)

    result = await db.execute(
        select(User).where(User.id == user_id, User.organization_id == org_id)
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    updates = data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to update"
        )

    if "role" in updates:
        _validate_role(updates["role"], user)
    if updates.get("is_active") is False and target.id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate yourself",
        )

    for field, value in updates.items():
        setattr(target, field, value)

    await log_action(
        db,
        action="user_updated",
        user_id=user.id,
        resource_type="user",
        resource_id=target.id,
        changes=updates,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(target)
    return target
