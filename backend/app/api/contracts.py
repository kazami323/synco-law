"""CRUD контрактов с версионированием и файлами в MinIO (Weeks 5-6, Task 1.8).

Видимость: view_all — все контракты организации; view_assigned (lawyer,
external) — только созданные самим пользователем.
"""

import asyncio
import csv
import hashlib
import io
import uuid
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from botocore.exceptions import ClientError
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.dependencies import get_current_user, get_upload_user
from app.core.permissions import ROLE_PERMISSIONS, require_permission
from app.db.base import get_db
from app.db.models import (
    Contract,
    Project,
    ContractDeadline,
    ContractType,
    ContractVersion,
    SignRequest,
    User,
    WorkflowState,
)
from app.db.schemas import (
    ContractCreate,
    ContractDeadlineCreate,
    ContractDeadlineOut,
    ContractDetail,
    ContractOut,
    ContractUpdate,
    ContractVersionOut,
    SignConfirmIn,
    SignConfirmOut,
    SignRequestOut,
    UpcomingDeadlineOut,
)
from app.services.deadlines import add_parsed_deadlines, days_left
from app.services.notifications import create_deadline_notifications, deliver
from app.services import search as search_service
from app.services.ai_usage import enforce_ai_access, record_ai_usage
from app.services.signature import (
    contract_hash,
    stub_signature,
    verify_pkcs7_via_dsv,
)
from app.utils.audit import log_action
from app.utils.document_parser import parse_file, pdf_needs_ocr
from app.utils.llm import collect_usage, extract_pdf_text
from app.utils.storage import open_download_stream, upload_file_async
from app.utils.upload_security import UploadSecurityError, secure_upload

router = APIRouter(prefix="/api/contracts", tags=["contracts"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
VALID_TYPES = {t.value for t in ContractType}


class ContractListResponse(BaseModel):
    total: int
    page: int
    items: list[ContractOut]


def _deadline_out(deadline: ContractDeadline, today: date | None = None) -> ContractDeadlineOut:
    return ContractDeadlineOut(
        id=deadline.id,
        contract_id=deadline.contract_id,
        deadline_date=deadline.deadline_date,
        type=deadline.deadline_type,
        days_left=days_left(deadline.deadline_date, today),
        is_notified=deadline.is_notified,
    )


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
    contract_id: uuid.UUID,
    user: User,
    db: AsyncSession,
    *,
    for_update: bool = False,
) -> Contract:
    """Контракт организации пользователя с учётом права видимости."""
    org_id = _require_org(user)
    query = (
        select(Contract)
        .where(Contract.id == contract_id, Contract.organization_id == org_id)
        # Плашки отдаём вместе с документом: ленивая подгрузка в async-сессии
        # выбросила бы MissingGreenlet при сериализации ответа.
        .options(selectinload(Contract.labels))
    )
    if for_update:
        query = query.with_for_update(of=Contract)
    result = await db.execute(query)
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
    project_id: uuid.UUID | None = None,
) -> Contract:
    if project_id is not None:
        project_exists = (
            await db.execute(
                select(Project.id).where(
                    Project.id == project_id,
                    Project.organization_id == user.organization_id,
                )
            )
        ).scalar_one_or_none()
        if project_exists is None:
            raise HTTPException(status_code=404, detail="Project not found")
    if contract_type not in VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid contract_type. Allowed: {sorted(VALID_TYPES)}",
        )
    contract = Contract(
        organization_id=user.organization_id,
        project_id=project_id,
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
    await add_parsed_deadlines(db, contract)
    pending_deliveries = await create_deadline_notifications(
        db, organization_id=user.organization_id
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
    await search_service.index_contract(contract)
    for recipient, text in pending_deliveries:
        await deliver(recipient, text)
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
        project_id=data.project_id,
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
    project_id: uuid.UUID | None = Form(None),
    file: UploadFile = File(...),
    user: User = Depends(get_upload_user),
    db: AsyncSession = Depends(get_db),
):
    """Создать контракт из файла PDF/DOCX/TXT: текст извлекается автоматически."""
    if "create" not in ROLE_PERMISSIONS.get(user.role, []):
        raise HTTPException(status_code=403, detail="Permission denied")
    org_id = _require_org(user)

    try:
        filename, data = await secure_upload(file)
        content = parse_file(filename, data)
        if pdf_needs_ocr(filename, content):
            await enforce_ai_access(db, user)
            with collect_usage() as usage:
                content = await extract_pdf_text(data, filename)
            record_ai_usage(db, user, usage, endpoint="pdf_ocr", agent="document_parser")
    except UploadSecurityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    file_path = await upload_file_async(data, filename, org_id)

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
        project_id=project_id,
    )


@router.get("/", response_model=ContractListResponse)
async def list_contracts(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    status_filter: str | None = None,
    q: str | None = None,
    project_id: uuid.UUID | None = None,
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
    if project_id is not None:
        query = query.where(Contract.project_id == project_id)
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
        # Один дополнительный запрос на всю страницу вместо N обращений из UI
        .options(selectinload(Contract.labels))
    )
    return ContractListResponse(
        total=total, page=page, items=list(result.scalars().all())
    )


@router.get("/export/csv")
async def export_registry_csv(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Реестр контрактов в CSV (UTF-8 BOM, ';' — открывается в Excel/1С)."""
    org_id = _require_org(user)
    perms = ROLE_PERMISSIONS.get(user.role, [])
    if "view_all" not in perms and "view_assigned" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied")

    query = select(Contract).where(Contract.organization_id == org_id)
    if "view_all" not in perms:
        query = query.where(Contract.created_by == user.id)
    rows = (
        (await db.execute(query.order_by(Contract.created_at))).scalars().all()
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        [
            "ID",
            "Название",
            "Тип",
            "Контрагент",
            "Сумма",
            "Валюта",
            "Статус",
            "Риск",
            "Создан",
            "Подписан",
        ]
    )
    for c in rows:
        writer.writerow(
            [
                str(c.id),
                c.title,
                c.contract_type or "",
                c.counterparty or "",
                f"{c.amount:.2f}".replace(".", ",") if c.amount is not None else "",
                c.currency,
                c.status,
                c.risk_score if c.risk_score is not None else "",
                c.created_at.strftime("%d.%m.%Y") if c.created_at else "",
                c.signed_at.strftime("%d.%m.%Y") if c.signed_at else "",
            ]
        )

    csv_bytes = "﻿" + buffer.getvalue()  # BOM для кириллицы в Excel
    filename = f"contracts_{date.today().isoformat()}.csv"
    return Response(
        content=csv_bytes.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/upcoming-deadlines", response_model=list[UpcomingDeadlineOut])
async def list_upcoming_deadlines(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = _require_org(user)
    perms = ROLE_PERMISSIONS.get(user.role, [])
    if "view_all" not in perms and "view_assigned" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied")

    today = date.today()
    window_end = today + timedelta(days=7)
    query = (
        select(ContractDeadline, Contract)
        .join(Contract, ContractDeadline.contract_id == Contract.id)
        .where(
            Contract.organization_id == org_id,
            ContractDeadline.deadline_date <= window_end,
            Contract.status != "archived",
        )
        .order_by(ContractDeadline.deadline_date)
        .limit(limit)
    )
    if "view_all" not in perms:
        query = query.where(Contract.created_by == user.id)

    rows = (await db.execute(query)).all()
    return [
        UpcomingDeadlineOut(
            id=deadline.id,
            contract_id=contract.id,
            contract_title=contract.title,
            deadline_date=deadline.deadline_date,
            type=deadline.deadline_type,
            days_left=days_left(deadline.deadline_date, today),
        )
        for deadline, contract in rows
    ]


@router.post("/{contract_id}/sign-request", response_model=SignRequestOut)
async def request_signature(
    contract_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("sign")),
    db: AsyncSession = Depends(get_db),
):
    contract = await get_visible_contract(contract_id, user, db, for_update=True)
    if contract.status != "ready_to_sign":
        raise HTTPException(
            status_code=409,
            detail="Contract must be ready_to_sign before E-IMZO signing",
        )

    digest = contract_hash(contract)
    sign_request = SignRequest(
        contract_id=contract.id,
        requested_by=user.id,
        contract_hash=digest,
    )
    db.add(sign_request)
    await db.flush()
    await log_action(
        db,
        action="sign_request_created",
        user_id=user.id,
        resource_type="contract",
        resource_id=contract.id,
        changes={"request_id": str(sign_request.id), "hash": digest},
        ip_address=_client_ip(request),
    )
    await db.commit()
    return SignRequestOut(request_id=sign_request.id, hash=digest)


@router.post("/{contract_id}/sign-confirm", response_model=SignConfirmOut)
async def confirm_signature(
    contract_id: uuid.UUID,
    request: Request,
    data: SignConfirmIn | None = None,
    user: User = Depends(require_permission("sign")),
    db: AsyncSession = Depends(get_db),
):
    contract = await get_visible_contract(contract_id, user, db, for_update=True)
    if contract.status != "ready_to_sign":
        raise HTTPException(
            status_code=409,
            detail="Contract must be ready_to_sign before E-IMZO signing",
        )

    query = select(SignRequest).where(
        SignRequest.contract_id == contract.id,
        SignRequest.status == "pending",
    )
    if data and data.request_id:
        query = query.where(SignRequest.id == data.request_id)
    query = query.order_by(SignRequest.created_at.desc()).limit(1).with_for_update()
    sign_request = (await db.execute(query)).scalar_one_or_none()
    if sign_request is None:
        raise HTTPException(status_code=404, detail="Pending sign request not found")

    digest = contract_hash(contract)
    if sign_request.contract_hash != digest:
        raise HTTPException(
            status_code=409,
            detail="Contract changed after sign request. Create a new sign request.",
        )

    is_real_signature = bool(data and data.signature)
    if not is_real_signature and not settings.ALLOW_STUB_SIGNATURES:
        raise HTTPException(
            status_code=400,
            detail="E-IMZO PKCS#7 signature is required",
        )
    if is_real_signature:
        # Реальный PKCS#7 от клиента E-IMZO; при настроенном DSV — проверяем
        if not data.certificate:
            raise HTTPException(status_code=400, detail="Сертификат подписанта обязателен")
        verdict = await verify_pkcs7_via_dsv(data.signature, digest)
        if verdict is not True:
            raise HTTPException(
                status_code=400,
                detail="Подпись не подтверждена E-IMZO DSV и не связана с хешем договора",
            )

    generated_signature, generated_certificate, generated_thumbprint = stub_signature(
        digest, sign_request.id
    )
    signature = data.signature if data and data.signature else generated_signature
    certificate = data.certificate if data and data.certificate else generated_certificate
    thumbprint = (
        hashlib.sha256(certificate.encode("utf-8")).hexdigest().upper()[:40]
        if is_real_signature
        else generated_thumbprint
    )

    now = datetime.now(timezone.utc)
    old_status = contract.status
    contract.status = "signed"
    contract.signed_at = now
    contract.signed_by = user.id
    contract.signature = signature
    contract.signature_timestamp = now
    contract.signature_certificate = certificate
    contract.certificate_thumbprint = thumbprint
    sign_request.status = "confirmed"
    sign_request.confirmed_at = now

    db.add(
        WorkflowState(
            contract_id=contract.id,
            current_stage="signed",
            approved_by=user.id,
            approved_at=now,
            comments=(
                "Подписано E-IMZO (PKCS#7)"
                if is_real_signature
                else "E-IMZO stub signature confirmed"
            ),
        )
    )
    await log_action(
        db,
        action="sign_confirmed",
        user_id=user.id,
        resource_type="contract",
        resource_id=contract.id,
        changes={
            "from": old_status,
            "to": contract.status,
            "request_id": str(sign_request.id),
            "signature_type": "eimzo" if is_real_signature else "stub",
        },
        ip_address=_client_ip(request),
    )
    await db.commit()
    await search_service.index_contract(contract)
    return SignConfirmOut(
        signature=signature,
        timestamp=now,
        certificate_thumbprint=thumbprint,
    )


@router.get("/{contract_id}", response_model=ContractDetail)
async def get_contract(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_visible_contract(contract_id, user, db)


@router.get("/{contract_id}/deadlines", response_model=list[ContractDeadlineOut])
async def get_deadlines(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contract = await get_visible_contract(contract_id, user, db)
    if await add_parsed_deadlines(db, contract):
        pending = await create_deadline_notifications(
            db, organization_id=user.organization_id
        )
        await db.commit()
        for recipient, text in pending:
            await deliver(recipient, text)

    today = date.today()
    result = await db.execute(
        select(ContractDeadline)
        .where(ContractDeadline.contract_id == contract.id)
        .order_by(ContractDeadline.deadline_date)
    )
    return [_deadline_out(deadline, today) for deadline in result.scalars().all()]


@router.post(
    "/{contract_id}/deadlines",
    response_model=ContractDeadlineOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_deadline(
    contract_id: uuid.UUID,
    data: ContractDeadlineCreate,
    request: Request,
    user: User = Depends(require_permission("edit")),
    db: AsyncSession = Depends(get_db),
):
    contract = await get_visible_contract(contract_id, user, db)
    deadline = ContractDeadline(
        contract_id=contract.id,
        deadline_date=data.deadline_date,
        deadline_type=data.type.strip()[:64] or "other",
    )
    db.add(deadline)
    await db.flush()
    pending = await create_deadline_notifications(
        db, organization_id=user.organization_id
    )
    await log_action(
        db,
        action="deadline_created",
        user_id=user.id,
        resource_type="contract",
        resource_id=contract.id,
        changes={"deadline_date": data.deadline_date.isoformat(), "type": data.type},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(deadline)
    for recipient, text in pending:
        await deliver(recipient, text)
    return _deadline_out(deadline, date.today())


@router.put("/{contract_id}", response_model=ContractDetail)
async def update_contract(
    contract_id: uuid.UUID,
    data: ContractUpdate,
    request: Request,
    user: User = Depends(require_permission("edit")),
    db: AsyncSession = Depends(get_db),
):
    """Обновить контракт; изменение текста создаёт новую версию."""
    contract = await get_visible_contract(contract_id, user, db, for_update=True)

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

    pending = []
    if content_changed:
        await add_parsed_deadlines(db, contract)
        pending = await create_deadline_notifications(
            db, organization_id=user.organization_id
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
    await search_service.index_contract(contract)
    for recipient, text in pending:
        await deliver(recipient, text)
    return contract


@router.delete("/{contract_id}")
async def archive_contract(
    contract_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("delete")),
    db: AsyncSession = Depends(get_db),
):
    """Мягкое удаление: контракт переводится в архив."""
    contract = await get_visible_contract(contract_id, user, db, for_update=True)
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
    await search_service.index_contract(contract)
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
    """Стримит исходный файл контракта из MinIO через бэкенд.

    Файл отдаём сами, а не presigned-ссылкой: в проде MinIO закрыт во внутренней
    сети и недоступен браузеру напрямую (ссылка вела бы на `minio:9000`).
    """
    contract = await get_visible_contract(contract_id, user, db)
    if not contract.file_path:
        raise HTTPException(status_code=404, detail="У контракта нет исходного файла")
    try:
        body, content_type, content_length = await asyncio.to_thread(
            open_download_stream, contract.file_path
        )
    except ClientError:
        raise HTTPException(status_code=404, detail="Исходный файл не найден в хранилище")

    filename = contract.file_path.rsplit("/", 1)[-1] or "document"

    def _iter():
        try:
            for chunk in body.iter_chunks(256 * 1024):
                yield chunk
        finally:
            body.close()

    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    if content_length is not None:
        headers["Content-Length"] = str(content_length)
    return StreamingResponse(_iter(), media_type=content_type, headers=headers)
