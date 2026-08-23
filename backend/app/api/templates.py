"""База шаблонов и каталоги (ТЗ, разделы 3.1 и 6)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.contracts import get_visible_contract
from app.core.dependencies import get_current_user
from app.core.document_types import catalogue as type_catalogue
from app.core.document_types import is_known_type, type_title
from app.core.permissions import require_permission
from app.core.statuses import catalogue as status_catalogue
from app.db.base import get_db
from app.db.models import ContractStatus, DocumentTemplate, User
from app.db.schemas import (
    TemplateCreate,
    TemplateDetail,
    TemplateFromContractIn,
    TemplateOut,
    TemplateUpdate,
)
from app.services import templates as template_service
from app.utils.audit import log_action

router = APIRouter(prefix="/api", tags=["templates"])


def _require_org(user: User) -> uuid.UUID:
    if user.organization_id is None:
        raise HTTPException(status_code=400, detail="Сначала создайте организацию")
    return user.organization_id


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _out(template: DocumentTemplate, *, detail: bool = False):
    payload = {
        column.name: getattr(template, column.name)
        for column in template.__table__.columns
    }
    payload["doc_type_title"] = type_title(template.doc_type)
    return TemplateDetail(**payload) if detail else TemplateOut(**payload)


# --------------------------------------------------------------------------
# Каталоги
# --------------------------------------------------------------------------


@router.get("/document-types")
async def document_types(group: str | None = Query(None)):
    """Каталог типов документов с обязательными блоками (ТЗ, раздел 3.1)."""
    return type_catalogue(group)


@router.get("/document-statuses")
async def document_statuses():
    """Каталог статусов: название, кто ставит, блокирует ли редактирование."""
    return status_catalogue()


# --------------------------------------------------------------------------
# Шаблоны
# --------------------------------------------------------------------------


@router.get("/templates", response_model=list[TemplateOut])
async def list_templates(
    doc_type: str | None = Query(None),
    include_archived: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = _require_org(user)
    rows = await template_service.list_templates(
        db, org_id, doc_type=doc_type, include_archived=include_archived
    )
    return [_out(row) for row in rows]


@router.get("/templates/{template_id}", response_model=TemplateDetail)
async def get_template(
    template_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = _require_org(user)
    template = await template_service.get_template(db, template_id, org_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    return _out(template, detail=True)


@router.post(
    "/templates", response_model=TemplateDetail, status_code=status.HTTP_201_CREATED
)
async def create_template(
    data: TemplateCreate,
    request: Request,
    user: User = Depends(require_permission("manage_templates")),
    db: AsyncSession = Depends(get_db),
):
    org_id = _require_org(user)
    if not is_known_type(data.doc_type):
        raise HTTPException(status_code=400, detail="Неизвестный тип документа")
    if not (data.content or "").strip():
        raise HTTPException(status_code=400, detail="Шаблон без текста")

    template = DocumentTemplate(
        organization_id=org_id,
        name=data.name.strip(),
        doc_type=data.doc_type,
        description=(data.description or "").strip() or None,
        content=data.content,
        actualized_at=datetime.now(timezone.utc).date(),
        created_by=user.id,
        created_by_name=user.full_name or user.username,
    )
    db.add(template)
    await log_action(
        db,
        action="template_created",
        user_id=user.id,
        resource_type="template",
        resource_id=None,
        changes={"name": template.name, "doc_type": template.doc_type},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(template)
    return _out(template, detail=True)


@router.post(
    "/contracts/{contract_id}/save-as-template",
    response_model=TemplateDetail,
    status_code=status.HTTP_201_CREATED,
)
async def save_contract_as_template(
    contract_id: uuid.UUID,
    data: TemplateFromContractIn,
    request: Request,
    user: User = Depends(require_permission("manage_templates")),
    db: AsyncSession = Depends(get_db),
):
    """Сохранить подтверждённый документ как шаблон (ТЗ, раздел 6).

    Только подтверждённый: шаблон, собранный из непроверенного черновика,
    тиражирует ошибку по всем будущим договорам.
    """
    org_id = _require_org(user)
    contract = await get_visible_contract(contract_id, user, db)
    allowed = {
        ContractStatus.APPROVED.value,
        ContractStatus.APPROVED_FINANCE.value,
        ContractStatus.READY_TO_SIGN.value,
        ContractStatus.SIGNED.value,
        ContractStatus.ARCHIVED.value,
    }
    if contract.status not in allowed:
        raise HTTPException(
            status_code=409,
            detail="В шаблон сохраняются только документы, подтверждённые юристом",
        )
    if not (contract.content or "").strip():
        raise HTTPException(status_code=400, detail="У документа нет текста")

    template = DocumentTemplate(
        organization_id=org_id,
        name=(data.name or f"Шаблон: {contract.title}").strip(),
        doc_type=contract.contract_type or "other",
        description=(data.description or "").strip() or None,
        content=contract.content,
        actualized_at=datetime.now(timezone.utc).date(),
        source_contract_id=contract.id,
        created_by=user.id,
        created_by_name=user.full_name or user.username,
    )
    db.add(template)
    await log_action(
        db,
        action="template_created_from_contract",
        user_id=user.id,
        resource_type="contract",
        resource_id=contract.id,
        changes={"name": template.name},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(template)
    return _out(template, detail=True)


@router.patch("/templates/{template_id}", response_model=TemplateDetail)
async def update_template(
    template_id: uuid.UUID,
    data: TemplateUpdate,
    request: Request,
    user: User = Depends(require_permission("manage_templates")),
    db: AsyncSession = Depends(get_db),
):
    org_id = _require_org(user)
    template = await template_service.get_template(db, template_id, org_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Шаблон не найден")

    updates = data.model_dump(exclude_unset=True)
    if "doc_type" in updates and not is_known_type(updates["doc_type"]):
        raise HTTPException(status_code=400, detail="Неизвестный тип документа")
    content_changed = "content" in updates and updates["content"] != template.content

    for field, value in updates.items():
        setattr(template, field, value)

    if content_changed:
        # Текст изменился — прежняя верификация к нему не относится.
        template_service.unverify(template)
        template.actualized_at = datetime.now(timezone.utc).date()

    await log_action(
        db,
        action="template_updated",
        user_id=user.id,
        resource_type="template",
        resource_id=template.id,
        changes={key: bool(value) if key == "content" else value for key, value in updates.items()},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(template)
    return _out(template, detail=True)


@router.post("/templates/{template_id}/verify", response_model=TemplateDetail)
async def verify_template(
    template_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("verify_template")),
    db: AsyncSession = Depends(get_db),
):
    """Отметка «верифицирован» с указанием юриста (ТЗ, раздел 6)."""
    org_id = _require_org(user)
    template = await template_service.get_template(db, template_id, org_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Шаблон не найден")

    template_service.verify(template, user)
    await log_action(
        db,
        action="template_verified",
        user_id=user.id,
        resource_type="template",
        resource_id=template.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(template)
    return _out(template, detail=True)


@router.delete("/templates/{template_id}", status_code=204)
async def archive_template(
    template_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("manage_templates")),
    db: AsyncSession = Depends(get_db),
):
    org_id = _require_org(user)
    template = await template_service.get_template(db, template_id, org_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    template.is_archived = True
    await log_action(
        db,
        action="template_archived",
        user_id=user.id,
        resource_type="template",
        resource_id=template.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
