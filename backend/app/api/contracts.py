"""CRUD контрактов с версионированием и файлами в MinIO (Weeks 5-6, Task 1.8).

Видимость: view_all — все контракты организации; view_assigned (lawyer,
external) — только созданные самим пользователем.
"""

import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.permissions import ROLE_PERMISSIONS, require_permission
from app.db.base import get_db
from app.db.models import Contract, ContractType, ContractVersion, User
from app.db.schemas import (
    ContractCreate,
    ContractDetail,
    ContractOut,
    ContractUpdate,
    ContractVersionOut,
)
from app.utils.audit import log_action
from app.utils.document_parser import parse_file
from app.utils.storage import presigned_download_url, upload_file

router = APIRouter(prefix="/api/contracts", tags=["contracts"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
VALID_TYPES = {t.value for t in ContractType}


class ContractListResponse(BaseModel):
    total: int
    page: int
    items: list[ContractOut]


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _require_org(user: User) -> uuid.UUID:
    if user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Create an organization first",
        )
    return user.organization_id


async def get_visible_contract(
    contract_id: uuid.UUID, user: User, db: AsyncSession
) -> Contract:
    """Контракт организации пользователя с учётом права видимости."""
    org_id = _require_org(user)
    result = await db.execute(
        select(Contract).where(
            Contract.id == contract_id, Contract.organization_id == org_id
        )
    )
    contract = result.scalar_one_or_none()
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")

    perms = ROLE_PERMISSIONS.get(user.role, [])
    if "view_all" in perms:
        return contract
    if "view_assigned" in perms and contract.created_by == user.id:
        return contract
    raise HTTPException(status_code=403, detail="Permission denied")


async def _create_contract_row(
    db: AsyncSession,
    user: User,
    *,
    title: str,
    contract_type: str,
    counterparty: str | None,
    content: str | None,
    amount: float | None,
    currency: str,
    file_path: str | None,
    ip: str | None,
) -> Contract:
    if contract_type not in VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid contract_type. Allowed: {sorted(VALID_TYPES)}",
        )
    contract = Contract(
        organization_id=user.organization_id,
        title=title,
        contract_type=contract_type,
        counterparty=counterparty,
        content=content,
        file_path=file_path,
        amount=amount,
        currency=currency,
        created_by=user.id,
    )
    db.add(contract)
    await db.flush()

    db.add(
        ContractVersion(
            contract_id=contract.id,
            version_number=1,
            content=content,
            changes_description="Первая версия",
            created_by=user.id,
        )
    )
    await log_action(
        db,
        action="contract_created",
        user_id=user.id,
        resource_type="contract",
        resource_id=contract.id,
        changes={"title": title, "contract_type": contract_type},
        ip_address=ip,
    )
    await db.commit()
    await db.refresh(contract)
    return contract


@router.post("/", response_model=ContractDetail, status_code=status.HTTP_201_CREATED)
async def create_contract(
    data: ContractCreate,
    request: Request,
    user: User = Depends(require_permission("create")),
    db: AsyncSession = Depends(get_db),
):
    """Создать контракт из текста."""
    _require_org(user)
    return await _create_contract_row(
        db,
        user,
        title=data.title,
        contract_type=data.contract_type,
        counterparty=data.counterparty,
        content=data.content,
        amount=data.amount,
        currency=data.currency,
        file_path=None,
        ip=_client_ip(request),
    )


@router.post(
    "/upload", response_model=ContractDetail, status_code=status.HTTP_201_CREATED
)
async def create_contract_from_file(
    request: Request,
    title: str = Form(...),
    contract_type: str = Form(...),
    counterparty: str | None = Form(None),
    amount: float | None = Form(None),
    currency: str = Form("UZS"),
    file: UploadFile = File(...),
    user: User = Depends(require_permission("create")),
    db: AsyncSession = Depends(get_db),
):
    """Создать контракт из файла PDF/DOCX/TXT: текст извлекается автоматически."""
    org_id = _require_org(user)

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Файл больше 20 МБ")
    try:
        content = parse_file(file.filename or "document", data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    file_path = upload_file(data, file.filename or "document", org_id)

    return await _create_contract_row(
        db,
        user,
        title=title,
        contract_type=contract_type,
        counterparty=counterparty,
        content=content,
        amount=amount,
        currency=currency,
        file_path=file_path,
        ip=_client_ip(request),
    )


@router.get("/", response_model=ContractListResponse)
async def list_contracts(
    page: int = 1,
    limit: int = 20,
    status_filter: str | None = None,
    q: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Контракты организации: поиск по названию/контрагенту, фильтр по статусу."""
    org_id = _require_org(user)
    perms = ROLE_PERMISSIONS.get(user.role, [])
    if "view_all" not in perms and "view_assigned" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied")

    query = select(Contract).where(Contract.organization_id == org_id)
    if "view_all" not in perms:
        query = query.where(Contract.created_by == user.id)
    if status_filter:
        query = query.where(Contract.status == status_filter)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            Contract.title.ilike(pattern) | Contract.counterparty.ilike(pattern)
        )

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    result = await db.execute(
        query.order_by(Contract.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return ContractListResponse(
        total=total, page=page, items=list(result.scalars().all())
    )


@router.get("/{contract_id}", response_model=ContractDetail)
async def get_contract(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_visible_contract(contract_id, user, db)


@router.put("/{contract_id}", response_model=ContractDetail)
async def update_contract(
    contract_id: uuid.UUID,
    data: ContractUpdate,
    request: Request,
    user: User = Depends(require_permission("edit")),
    db: AsyncSession = Depends(get_db),
):
    """Обновить контракт; изменение текста создаёт новую версию."""
    contract = await get_visible_contract(contract_id, user, db)

    updates = data.model_dump(exclude_unset=True)
    changes_description = updates.pop("changes_description", None)
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")

    content_changed = (
        "content" in updates and updates["content"] != contract.content
    )

    for field, value in updates.items():
        setattr(contract, field, value)

    if content_changed:
        last = (
            await db.execute(
                select(func.max(ContractVersion.version_number)).where(
                    ContractVersion.contract_id == contract.id
                )
            )
        ).scalar_one()
        db.add(
            ContractVersion(
                contract_id=contract.id,
                version_number=(last or 0) + 1,
                content=updates["content"],
                changes_description=changes_description or "Изменение текста",
                created_by=user.id,
            )
        )

    await log_action(
        db,
        action="contract_updated",
        user_id=user.id,
        resource_type="contract",
        resource_id=contract.id,
        changes={k: bool(v) if k == "content" else v for k, v in updates.items()},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(contract)
    return contract


@router.delete("/{contract_id}")
async def archive_contract(
    contract_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("delete")),
    db: AsyncSession = Depends(get_db),
):
    """Мягкое удаление: контракт переводится в архив."""
    contract = await get_visible_contract(contract_id, user, db)
    contract.status = "archived"
    await log_action(
        db,
        action="contract_archived",
        user_id=user.id,
        resource_type="contract",
        resource_id=contract.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    return {"message": "Contract archived"}


@router.get("/{contract_id}/versions", response_model=list[ContractVersionOut])
async def get_versions(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contract = await get_visible_contract(contract_id, user, db)
    result = await db.execute(
        select(ContractVersion)
        .where(ContractVersion.contract_id == contract.id)
        .order_by(ContractVersion.version_number.desc())
    )
    return list(result.scalars().all())


@router.get("/{contract_id}/download")
async def download_original(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Временная ссылка на исходный файл в MinIO."""
    contract = await get_visible_contract(contract_id, user, db)
    if not contract.file_path:
        raise HTTPException(status_code=404, detail="У контракта нет исходного файла")
    return {"url": presigned_download_url(contract.file_path)}
