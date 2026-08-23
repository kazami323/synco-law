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
from app.db.models import Contract, Project, ProjectMember, User
from app.db.schemas import (
    ProjectContextIn,
    ProjectCreate,
    ProjectMemberIn,
    ProjectMemberOut,
    ProjectOut,
    ProjectUpdate,
)
from app.services import project_access
from app.utils.audit import log_action

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _require_org(user: User) -> uuid.UUID:
    if user.organization_id is None:
        raise HTTPException(status_code=400, detail="У пользователя нет организации")
    return user.organization_id


def _require_create(user: User) -> None:
    if "create" not in ROLE_PERMISSIONS.get(user.role, []):
        raise HTTPException(status_code=403, detail="Недостаточно прав для этого действия")


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
        raise HTTPException(status_code=404, detail="Проект не найден")
    hidden = await project_access.hidden_project_ids(db, user)
    if project.id in hidden:
        raise HTTPException(status_code=404, detail="Проект не найден")
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
    hidden = await project_access.hidden_project_ids(db, user)
    if hidden:
        query = query.where(Project.id.not_in(hidden))
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
            raise HTTPException(status_code=400, detail="Недопустимый статус")
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


# --------------------------------------------------------------------------
# Контекст проекта и участники (ТЗ, раздел 1)
# --------------------------------------------------------------------------


@router.get("/{project_id}/context")
async def get_context(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Общий контекст проекта: стороны, суммы, сроки."""
    project = await _get_project(project_id, user, db)
    return project.context or {}


@router.put("/{project_id}/context")
async def set_context(
    project_id: uuid.UUID,
    data: ProjectContextIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Задать контекст проекта.

    Контекст наследуется документами при генерации: юрист вводит стороны,
    суммы и сроки один раз на проект, а не в каждый договор.
    """
    _require_create(user)
    project = await _get_project(project_id, user, db)
    payload = data.model_dump(exclude_none=True, mode="json")
    project.context = payload or None
    await log_action(
        db,
        action="project_context_updated",
        user_id=user.id,
        resource_type="project",
        resource_id=project.id,
        changes={"fields": sorted(payload)},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return payload


@router.get("/{project_id}/members", response_model=list[ProjectMemberOut])
async def list_members(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    rows = (
        await db.execute(
            select(ProjectMember, User)
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id == project.id)
            .order_by(ProjectMember.created_at)
        )
    ).all()
    return [
        ProjectMemberOut(
            id=member.id,
            user_id=member.user_id,
            access=member.access,
            full_name=member_user.full_name,
            email=member_user.email,
            role=member_user.role,
            created_at=member.created_at,
        )
        for member, member_user in rows
    ]


@router.post("/{project_id}/members", response_model=ProjectMemberOut, status_code=201)
async def add_member(
    project_id: uuid.UUID,
    data: ProjectMemberIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Добавить участника проекта с правом доступа."""
    _require_create(user)
    org_id = _require_org(user)
    project = await _get_project(project_id, user, db)
    if data.access not in ("read", "comment", "write"):
        raise HTTPException(
            status_code=400, detail="Допустимый доступ: read, comment, write"
        )

    member_user = (
        await db.execute(
            select(User).where(
                User.id == data.user_id, User.organization_id == org_id
            )
        )
    ).scalar_one_or_none()
    if member_user is None:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    existing = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == data.user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.access = data.access
        member = existing
    else:
        member = ProjectMember(
            project_id=project.id,
            user_id=data.user_id,
            access=data.access,
            added_by=user.id,
        )
        db.add(member)

    await log_action(
        db,
        action="project_member_added",
        user_id=user.id,
        resource_type="project",
        resource_id=project.id,
        changes={"user_id": str(data.user_id), "access": data.access},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(member)
    return ProjectMemberOut(
        id=member.id,
        user_id=member.user_id,
        access=member.access,
        full_name=member_user.full_name,
        email=member_user.email,
        role=member_user.role,
        created_at=member.created_at,
    )


@router.delete("/{project_id}/members/{member_id}", status_code=204)
async def remove_member(
    project_id: uuid.UUID,
    member_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_create(user)
    project = await _get_project(project_id, user, db)
    member = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.id == member_id,
                ProjectMember.project_id == project.id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    await db.delete(member)
    await log_action(
        db,
        action="project_member_removed",
        user_id=user.id,
        resource_type="project",
        resource_id=project.id,
        changes={"user_id": str(member.user_id)},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
