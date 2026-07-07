"""Проекты (дела/заказы): папки, в которых юрист ведёт договоры и
документы одного клиента или заказа.

Видят проекты все сотрудники организации; создаёт и редактирует любой,
у кого есть право create (admin/head/senior_lawyer/lawyer). Договоры
внутри проекта отфильтрованы правами видимости пользователя.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.permissions import ROLE_PERMISSIONS
from app.db.base import get_db
from app.db.models import Contract, Project, User
from app.db.schemas import ProjectCreate, ProjectOut, ProjectUpdate
from app.utils.audit import log_action

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _require_org(user: User) -> uuid.UUID:
    if user.organization_id is None:
        raise HTTPException(status_code=400, detail="User has no organization")
    return user.organization_id


def _require_create(user: User) -> None:
    if "create" not in ROLE_PERMISSIONS.get(user.role, []):
        raise HTTPException(status_code=403, detail="Permission denied")


async def _get_project(
    project_id: uuid.UUID, user: User, db: AsyncSession
) -> Project:
    org_id = _require_org(user)
    project = (
        await db.execute(
            select(Project).where(
                Project.id == project_id, Project.organization_id == org_id
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _to_out(project: Project, contracts_count: int) -> ProjectOut:
    out = ProjectOut.model_validate(project)
    out.contracts_count = contracts_count
    return out


@router.get("/", response_model=list[ProjectOut])
async def list_projects(
    status_filter: str | None = None,
    q: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Проекты организации с числом договоров в каждом."""
    org_id = _require_org(user)
    query = (
        select(Project, func.count(Contract.id))
        .outerjoin(Contract, Contract.project_id == Project.id)
        .where(Project.organization_id == org_id)
        .group_by(Project.id)
        .order_by(Project.created_at.desc())
    )
    if status_filter:
        query = query.where(Project.status == status_filter)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            Project.name.ilike(pattern) | Project.client.ilike(pattern)
        )
    rows = (await db.execute(query)).all()
    return [_to_out(project, count) for project, count in rows]


@router.post("/", response_model=ProjectOut, status_code=201)
async def create_project(
    data: ProjectCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = _require_org(user)
    _require_create(user)
    project = Project(
        organization_id=org_id,
        name=data.name,
        client=data.client,
        description=data.description,
        created_by=user.id,
    )
    db.add(project)
    await db.flush()
    await log_action(
        db,
        action="project_created",
        user_id=user.id,
        resource_type="project",
        resource_id=project.id,
        changes={"name": data.name},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(project)
    return _to_out(project, 0)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    count = (
        await db.execute(
            select(func.count())
            .select_from(Contract)
            .where(Contract.project_id == project.id)
        )
    ).scalar_one()
    return _to_out(project, count)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_create(user)
    project = await _get_project(project_id, user, db)

    changes: dict[str, str | None] = {}
    if data.name is not None:
        project.name = data.name
        changes["name"] = data.name
    if data.client is not None:
        project.client = data.client
        changes["client"] = data.client
    if data.description is not None:
        project.description = data.description
        changes["description"] = data.description
    if data.status is not None:
        if data.status not in ("active", "closed"):
            raise HTTPException(status_code=400, detail="Invalid status")
        project.status = data.status
        changes["status"] = data.status

    await log_action(
        db,
        action="project_updated",
        user_id=user.id,
        resource_type="project",
        resource_id=project.id,
        changes=changes,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(project)
    count = (
        await db.execute(
            select(func.count())
            .select_from(Contract)
            .where(Contract.project_id == project.id)
        )
    ).scalar_one()
    return _to_out(project, count)
