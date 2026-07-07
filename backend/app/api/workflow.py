"""Workflow согласования контрактов (Weeks 9-10).

Цепочка: draft → [AI-анализ] → analyzed → approved (юристы) →
approved_finance (финансы) → ready_to_sign → signed.
Каждый переход пишется в workflow_states и аудит-лог.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.contracts import get_visible_contract
from app.core.dependencies import get_current_user
from app.core.permissions import ROLE_PERMISSIONS
from app.db.base import get_db
from app.db.models import Contract, User, WorkflowState
from app.services import search as search_service
from app.services.notifications import deliver, record_notification
from app.services.signature import contract_hash, stub_signature
from app.utils.audit import log_action

router = APIRouter(prefix="/api", tags=["workflow"])

# Действие → (из каких статусов, новый статус, требуемое право)
ACTIONS: dict[str, dict] = {
    "approve_legal": {
        "from": {"draft", "analyzed"},
        "to": "approved",
        "permission": "approve",
        "stage": "approved",
    },
    "approve_finance": {
        "from": {"approved"},
        "to": "approved_finance",
        "permission": "approve_finance",
        "stage": "approved_finance",
    },
    "finalize": {
        "from": {"approved_finance"},
        "to": "ready_to_sign",
        "permission": "approve",
        "stage": "ready_to_sign",
    },
    # Пока простая отметка о подписании; реальный E-IMZO — Weeks 11-12
    "sign": {
        "from": {"ready_to_sign"},
        "to": "signed",
        "permission": "sign",
        "stage": "signed",
    },
    "reject": {
        "from": {"analyzed", "approved", "approved_finance", "ready_to_sign"},
        "to": "draft",
        "permission": None,  # любой, кто может согласовывать
        "stage": "rejected",
    },
}

REVIEWER_PERMISSIONS = {"approve", "approve_finance", "sign"}


def _user_can(user: User, action: str) -> bool:
    if user.role == "admin":
        return True
    rights = set(ROLE_PERMISSIONS.get(user.role, []))
    need = ACTIONS[action]["permission"]
    if need is None:  # reject доступен любому согласующему
        return bool(rights & REVIEWER_PERMISSIONS)
    return need in rights


def available_actions(user: User, status: str) -> list[str]:
    return [
        name
        for name, spec in ACTIONS.items()
        if status in spec["from"] and _user_can(user, name)
    ]


class TransitionRequest(BaseModel):
    comment: str | None = None


# Кого звать на следующий шаг: новый статус → право, дающее ход
NEXT_STEP_PERMISSION: dict[str, str] = {
    "analyzed": "approve",
    "approved": "approve_finance",
    "approved_finance": "approve",
    "ready_to_sign": "sign",
}

ACTION_LABELS = {
    "approve_legal": "юридически согласован",
    "approve_finance": "согласован финансовым отделом",
    "finalize": "передан на подписание",
    "sign": "подписан",
    "reject": "отклонён",
}


def _roles_with(permission: str) -> list[str]:
    return [
        role for role, rights in ROLE_PERMISSIONS.items() if permission in rights
    ]


async def _workflow_notifications(
    db: AsyncSession, contract: Contract, action: str, actor: User, comment: str | None
) -> list[tuple[User, str]]:
    """Внутрисистемные уведомления о переходе; возвращает пары для доставки."""
    pending: list[tuple[User, str]] = []
    actor_name = actor.full_name or actor.username
    label = ACTION_LABELS.get(action, action)

    # Автору контракта — о любом чужом действии
    if contract.created_by and contract.created_by != actor.id:
        author = await db.get(User, contract.created_by)
        if author and author.is_active:
            text = f"Контракт «{contract.title}» {label} ({actor_name})"
            if comment:
                text += f": {comment}"
            record_notification(db, author, text, contract.id)
            pending.append((author, text))

    # Следующей роли в цепочке — что контракт ждёт их шага
    need = NEXT_STEP_PERMISSION.get(contract.status)
    if need:
        reviewers = (
            (
                await db.execute(
                    select(User).where(
                        User.organization_id == contract.organization_id,
                        User.is_active.is_(True),
                        User.role.in_(_roles_with(need)),
                    )
                )
            )
            .scalars()
            .all()
        )
        text = f"Контракт «{contract.title}» ожидает вашего шага: {STAGE_WAIT_LABELS.get(contract.status, contract.status)}"
        for reviewer in reviewers:
            if reviewer.id == actor.id or reviewer.id == contract.created_by:
                continue
            record_notification(db, reviewer, text, contract.id)
            pending.append((reviewer, text))
    return pending


STAGE_WAIT_LABELS = {
    "analyzed": "юридическое согласование",
    "approved": "финансовое согласование",
    "approved_finance": "передача на подписание",
    "ready_to_sign": "подписание",
}


@router.get("/contracts/{contract_id}/workflow")
async def get_workflow(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contract = await get_visible_contract(contract_id, user, db)

    rows = (
        await db.execute(
            select(WorkflowState, User.full_name, User.username)
            .outerjoin(User, WorkflowState.approved_by == User.id)
            .where(WorkflowState.contract_id == contract.id)
            .order_by(WorkflowState.created_at)
        )
    ).all()

    return {
        "contract_id": str(contract.id),
        "status": contract.status,
        "available_actions": available_actions(user, contract.status),
        "history": [
            {
                "stage": state.current_stage,
                "comment": state.comments,
                "at": state.approved_at,
                "by": full_name or username,
            }
            for state, full_name, username in rows
        ],
    }


@router.post("/contracts/{contract_id}/workflow/{action}")
async def transition(
    contract_id: uuid.UUID,
    action: str,
    request: Request,
    data: TransitionRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if action not in ACTIONS:
        raise HTTPException(
            status_code=404, detail=f"Неизвестное действие. Доступны: {sorted(ACTIONS)}"
        )
    spec = ACTIONS[action]
    contract = await get_visible_contract(contract_id, user, db)

    if not _user_can(user, action):
        raise HTTPException(status_code=403, detail="Недостаточно прав для этого шага")
    if contract.status not in spec["from"]:
        raise HTTPException(
            status_code=409,
            detail=f"Действие «{action}» недоступно из статуса «{contract.status}»",
        )
    comment = data.comment if data else None
    if action == "reject" and not (comment and comment.strip()):
        raise HTTPException(
            status_code=400, detail="При отклонении обязателен комментарий"
        )

    now = datetime.now(timezone.utc)
    old_status = contract.status
    contract.status = spec["to"]
    if action == "sign":
        contract.signed_at = now
        contract.signed_by = user.id
        signature, certificate, thumbprint = stub_signature(contract_hash(contract), uuid.uuid4())
        contract.signature = signature
        contract.signature_timestamp = now
        contract.signature_certificate = certificate
        contract.certificate_thumbprint = thumbprint

    db.add(
        WorkflowState(
            contract_id=contract.id,
            current_stage=spec["stage"],
            approved_by=user.id,
            approved_at=now,
            comments=comment,
        )
    )
    await log_action(
        db,
        action=f"workflow_{action}",
        user_id=user.id,
        resource_type="contract",
        resource_id=contract.id,
        changes={"from": old_status, "to": contract.status, "comment": comment},
        ip_address=request.client.host if request.client else None,
    )
    pending = await _workflow_notifications(db, contract, action, user, comment)
    await db.commit()
    await search_service.index_contract(contract)
    for recipient, text in pending:
        await deliver(recipient, text)

    return {
        "status": contract.status,
        "available_actions": available_actions(user, contract.status),
    }
