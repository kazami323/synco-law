"""Организации: создание, просмотр и редактирование (Weeks 3-4).

Флоу онбординга: пользователь регистрируется -> создаёт организацию ->
автоматически становится её админом -> добавляет сотрудников через /api/users.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.base import get_db
from app.db.models import Organization, Role, User
from app.db.schemas import OrganizationCreate, OrganizationOut, OrganizationUpdate
from app.services.rate_limit import enforce_limit
from app.utils.audit import log_action

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


class OrganizationJoinRequest(BaseModel):
    invite_code: str


@router.post("/", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrganizationCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Создать организацию; создатель становится её админом."""
    if user.organization_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already belongs to an organization",
        )

    org = Organization(
        name=data.name, email=data.email, phone=data.phone, address=data.address
    )
    db.add(org)
    await db.flush()  # получаем org.id до коммита

    user.organization_id = org.id
    user.role = Role.ADMIN.value

    await log_action(
        db,
        action="organization_created",
        user_id=user.id,
        resource_type="organization",
        resource_id=org.id,
        changes={"name": data.name},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(org)
    return org


@router.post("/join", response_model=OrganizationOut)
async def join_organization(
    data: OrganizationJoinRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Join an existing organization by invite code."""
    if user.organization_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already belongs to an organization",
        )
    await enforce_limit(
        f"organization:join:{user.id}", limit=10, window_seconds=60 * 60
    )

    invite_code = data.invite_code.strip().upper()
    if not invite_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite code is required",
        )

    result = await db.execute(
        select(Organization).where(Organization.invite_code == invite_code)
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization invite code not found",
        )

    user.organization_id = org.id
    user.role = Role.LAWYER.value

    await log_action(
        db,
        action="organization_joined",
        user_id=user.id,
        resource_type="organization",
        resource_id=org.id,
        changes={"invite_code": invite_code},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(org)
    return org


@router.get("/me", response_model=OrganizationOut)
async def get_my_organization(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User does not belong to an organization",
        )
    result = await db.execute(
        select(Organization).where(Organization.id == user.organization_id)
    )
    return result.scalar_one()


@router.put("/me", response_model=OrganizationOut)
async def update_my_organization(
    data: OrganizationUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Обновить данные организации (только admin/head)."""
    if user.role not in (Role.ADMIN.value, Role.HEAD.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied"
        )
    if user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User does not belong to an organization",
        )

    result = await db.execute(
        select(Organization).where(Organization.id == user.organization_id)
    )
    org = result.scalar_one()

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(org, field, value)

    await log_action(
        db,
        action="organization_updated",
        user_id=user.id,
        resource_type="organization",
        resource_id=org.id,
        changes=updates,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(org)
    return org
