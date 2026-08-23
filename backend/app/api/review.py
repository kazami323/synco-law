"""API правового движка: пункты, модули проверки, находки, комментарии.

Реализует раздел 4 ТЗ. Главное правило, которое живёт именно здесь, а не в
интерфейсе: решение по каждому пункту принимает юрист, и оно фиксируется с
автором и временем. Система только предлагает.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.risk_agent import RISK_CATEGORIES, RISK_LEVELS
from app.api.contracts import ensure_no_running_review, get_visible_contract
from app.core.dependencies import get_current_user
from app.core.permissions import require_permission
from app.core.statuses import is_locked
from app.db.base import get_db
from app.db.models import (
    Clause,
    ClauseDecision,
    ClauseDecisionAction,
    Contract,
    ContractVersion,
    DocumentComment,
    LogicFinding,
    ReviewRun,
    RiskFinding,
    User,
)
from app.db.schemas import (
    ClauseDecisionIn,
    ClauseDecisionOut,
    ClauseListOut,
    ClauseOut,
    CommentCreate,
    CommentOut,
    FindingResolveIn,
    LogicFindingOut,
    ReviewRunOut,
    ReviewStartIn,
    RiskFindingOut,
)
from app.services import clauses as clause_service
from app.services.clause_splitter import content_hash as clause_content_hash
from app.services import review as review_service
from app.services.ai_usage import enforce_ai_access
from app.services.logic_check import LOGIC_CATEGORIES
from app.utils.audit import log_action
from app.utils.llm import require_api_key

router = APIRouter(prefix="/api", tags=["review"])

_BACKGROUND_TASKS: set[asyncio.Task] = set()

FINDING_STATUSES = {"open", "accepted", "rejected", "fixed"}


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# --------------------------------------------------------------------------
# Пункты документа
# --------------------------------------------------------------------------


@router.get("/contracts/{contract_id}/clauses", response_model=ClauseListOut)
async def list_clauses(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Пункты документа с вердиктами системы и решениями юриста."""
    contract = await get_visible_contract(contract_id, user, db)
    stored = await clause_service.get_clauses(db, contract.id)
    if not stored and contract.content:
        # Раньше дерево строилось прямо здесь. Два одновременных открытия
        # страницы (или чтение параллельно с правкой) удаляли и пересоздавали
        # пункты в двух транзакциях, и часть решений юриста терялась молча.
        # Берём блокировку документа и перепроверяем под ней.
        contract = await get_visible_contract(contract_id, user, db, for_update=True)
        stored = await clause_service.get_clauses(db, contract.id)
        if not stored:
            await clause_service.rebuild_clauses(db, contract)
        await db.commit()
        stored = await clause_service.get_clauses(db, contract.id)

    return await _clause_list_payload(db, contract, stored)


@router.post("/contracts/{contract_id}/clauses/rebuild", response_model=ClauseListOut)
async def rebuild_clauses(
    contract_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("edit")),
    db: AsyncSession = Depends(get_db),
):
    """Пересобрать дерево пунктов из текущего текста документа.

    Подтверждения по пунктам, текст которых не менялся, сохраняются.
    """
    contract = await get_visible_contract(contract_id, user, db, for_update=True)
    _ensure_editable(contract)
    # Та же причина, что и для правки текста: пересборка удаляет строки
    # пунктов, на которые идущий прогон уже ссылается.
    await ensure_no_running_review(db, contract)
    await clause_service.rebuild_clauses(db, contract)
    await log_action(
        db,
        action="clauses_rebuilt",
        user_id=user.id,
        resource_type="contract",
        resource_id=contract.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    stored = await clause_service.get_clauses(db, contract.id)
    return await _clause_list_payload(db, contract, stored)


@router.post("/clauses/{clause_id}/decision", response_model=ClauseDecisionOut)
async def decide_clause(
    clause_id: uuid.UUID,
    data: ClauseDecisionIn,
    request: Request,
    user: User = Depends(require_permission("confirm_clause")),
    db: AsyncSession = Depends(get_db),
):
    """Решение юриста по пункту: подтвердить / изменить / комментарий / отложить."""
    action = (data.action or "").strip().lower()
    valid = {item.value for item in ClauseDecisionAction}
    if action not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимое действие. Допустимы: {', '.join(sorted(valid))}",
        )

    clause = await db.get(Clause, clause_id)
    if clause is None:
        raise HTTPException(status_code=404, detail="Пункт не найден")
    # Права проверяются через документ: пункт сам по себе доступа не даёт.
    contract = await get_visible_contract(clause.contract_id, user, db, for_update=True)
    _ensure_editable(contract)

    previous_text = clause.content
    anchor = clause.anchor
    if action == ClauseDecisionAction.EDIT.value:
        new_text = (data.new_text or "").strip()
        if not new_text:
            raise HTTPException(
                status_code=400, detail="Для действия «Изменить» нужен новый текст пункта"
            )
        # Правка пункта пересобирает дерево ниже по коду — во время идущего
        # прогона это ломает его на внешнем ключе. Остальные три действия
        # (подтвердить, комментарий, отложить) текст не трогают и разрешены.
        await ensure_no_running_review(db, contract)
        clause.content = new_text
        clause.content_hash = clause_content_hash(new_text)

    # Актуально только последнее решение; прошлые остаются историей.
    await db.execute(
        update(ClauseDecision)
        .where(
            ClauseDecision.clause_id == clause.id,
            ClauseDecision.is_current.is_(True),
        )
        .values(is_current=False)
    )

    decision = ClauseDecision(
        clause_id=clause.id,
        action=action,
        comment=(data.comment or "").strip() or None,
        previous_text=previous_text if action == ClauseDecisionAction.EDIT.value else None,
        new_text=clause.content if action == ClauseDecisionAction.EDIT.value else None,
        clause_hash=clause.content_hash,
        is_current=True,
        decided_by=user.id,
        decided_by_name=user.full_name or user.username,
    )
    db.add(decision)

    if action == ClauseDecisionAction.EDIT.value:
        # Правка пункта меняет текст договора: вставляем новую редакцию на
        # место старой по границам пункта. Пересобирать документ из пунктов
        # нельзя — так теряются «Раздел», римская нумерация и маркеры
        # подпунктов. Каждая правка создаёт версию (ТЗ, раздел 5).
        await db.flush()
        try:
            contract.content = clause_service.apply_clause_edit(
                contract.content or "", clause, clause.content
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        # Границы всех пунктов сдвинулись — пересобираем дерево, решения
        # переносятся по якорям.
        await clause_service.rebuild_clauses(db, contract)

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
                content=contract.content,
                changes_description=f"Правка пункта {clause.anchor}",
                created_by=user.id,
            )
        )

    await log_action(
        db,
        action="clause_decision",
        user_id=user.id,
        resource_type="clause",
        resource_id=clause.id,
        changes={
            "contract_id": str(contract.id),
            "anchor": clause.anchor,
            "action": action,
        },
        ip_address=_client_ip(request),
    )
    await db.commit()

    # После правки дерево пунктов пересобрано: и пункт, и решение — это уже
    # новые строки (старые ушли каскадом). Поэтому отвечаем тем, что реально
    # лежит в базе, а не объектом, который держали в памяти до пересборки.
    stored = await clause_service.get_clauses(db, contract.id)
    fresh = next((item for item in stored if item.anchor == anchor), None)
    if fresh is None:
        raise HTTPException(
            status_code=409,
            detail="Пункт исчез после пересборки документа. Откройте документ заново.",
        )
    current = await clause_service.current_decisions(db, [fresh.id])
    saved = current.get(fresh.id)
    if saved is None:
        raise HTTPException(status_code=409, detail="Решение не сохранилось")
    return _decision_out(saved, fresh.content_hash)


@router.get("/clauses/{clause_id}/history", response_model=list[ClauseDecisionOut])
async def clause_history(
    clause_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """История решений по пункту — для разбора спорных ситуаций постфактум."""
    clause = await db.get(Clause, clause_id)
    if clause is None:
        raise HTTPException(status_code=404, detail="Пункт не найден")
    await get_visible_contract(clause.contract_id, user, db)

    rows = (
        (
            await db.execute(
                select(ClauseDecision)
                .where(ClauseDecision.clause_id == clause_id)
                .order_by(ClauseDecision.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_decision_out(row, clause.content_hash) for row in rows]


# --------------------------------------------------------------------------
# Модули проверки
# --------------------------------------------------------------------------


@router.post("/contracts/{contract_id}/review", response_model=list[ReviewRunOut])
async def start_review(
    contract_id: uuid.UUID,
    data: ReviewStartIn,
    user: User = Depends(require_permission("run_review")),
    db: AsyncSession = Depends(get_db),
):
    """Запуск модулей проверки — по отдельности или всех сразу (ТЗ, раздел 4)."""
    require_api_key()
    await enforce_ai_access(db, user)
    contract = await get_visible_contract(contract_id, user, db, for_update=True)
    if is_locked(contract.status):
        raise HTTPException(
            status_code=409,
            detail="Документ в финальном статусе: проверки не запускаются",
        )
    if db.bind is None:
        raise HTTPException(status_code=503, detail="База данных временно недоступна")

    modules = data.modules or list(review_service.ALL_MODULES)
    try:
        runs = await review_service.create_runs(
            db, contract, user, modules, party_side=data.party_side
        )
    except review_service.ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.commit()
    for run in runs:
        await db.refresh(run)

    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    for run in runs:
        _spawn(review_service.perform_run(run.id, user.id, factory))
    return runs


@router.get("/contracts/{contract_id}/review")
async def review_summary(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Сводка по документу (ТЗ, раздел 5)."""
    contract = await get_visible_contract(contract_id, user, db)
    return await review_service.summary(db, contract)


@router.get("/contracts/{contract_id}/review/runs", response_model=list[ReviewRunOut])
async def review_runs(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contract = await get_visible_contract(contract_id, user, db)
    rows = (
        (
            await db.execute(
                select(ReviewRun)
                .where(ReviewRun.contract_id == contract.id)
                .order_by(ReviewRun.started_at.desc())
                .limit(30)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


# --------------------------------------------------------------------------
# Находки Модулей 2 и 3
# --------------------------------------------------------------------------


@router.get(
    "/contracts/{contract_id}/logic-findings", response_model=list[LogicFindingOut]
)
async def list_logic_findings(
    contract_id: uuid.UUID,
    only_open: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contract = await get_visible_contract(contract_id, user, db)
    query = select(LogicFinding).where(LogicFinding.contract_id == contract.id)
    if only_open:
        query = query.where(LogicFinding.status == "open")
    rows = (
        (await db.execute(query.order_by(LogicFinding.created_at))).scalars().all()
    )
    return [
        _logic_out(row) for row in rows
    ]


@router.patch("/logic-findings/{finding_id}", response_model=LogicFindingOut)
async def resolve_logic_finding(
    finding_id: uuid.UUID,
    data: FindingResolveIn,
    request: Request,
    user: User = Depends(require_permission("confirm_clause")),
    db: AsyncSession = Depends(get_db),
):
    """Принять правку, отклонить или отметить исправленной вручную."""
    finding = await db.get(LogicFinding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Расхождение не найдено")
    contract = await get_visible_contract(finding.contract_id, user, db)
    # Запись проверки — часть доказательной базы: после подписания нельзя
    # задним числом отметить расхождение устранённым.
    _ensure_findings_open(contract)
    _apply_resolution(finding, data, user)
    await log_action(
        db,
        action="logic_finding_resolved",
        user_id=user.id,
        resource_type="logic_finding",
        resource_id=finding.id,
        changes={"status": finding.status, "contract_id": str(finding.contract_id)},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(finding)
    return _logic_out(finding)


@router.get(
    "/contracts/{contract_id}/risk-findings", response_model=list[RiskFindingOut]
)
async def list_risk_findings(
    contract_id: uuid.UUID,
    only_open: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contract = await get_visible_contract(contract_id, user, db)
    query = select(RiskFinding).where(RiskFinding.contract_id == contract.id)
    if only_open:
        query = query.where(RiskFinding.status == "open")
    rows = (await db.execute(query.order_by(RiskFinding.created_at))).scalars().all()
    # Высокие риски первыми: юрист смотрит сверху и должен увидеть критичное.
    rows = sorted(rows, key=lambda item: (_level_order(item.level), item.created_at))
    return [
        _risk_out(row) for row in rows
    ]


@router.patch("/risk-findings/{finding_id}", response_model=RiskFindingOut)
async def resolve_risk_finding(
    finding_id: uuid.UUID,
    data: FindingResolveIn,
    request: Request,
    user: User = Depends(require_permission("confirm_clause")),
    db: AsyncSession = Depends(get_db),
):
    finding = await db.get(RiskFinding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Риск не найден")
    contract = await get_visible_contract(finding.contract_id, user, db)
    _ensure_findings_open(contract)
    _apply_resolution(finding, data, user)
    await log_action(
        db,
        action="risk_finding_resolved",
        user_id=user.id,
        resource_type="risk_finding",
        resource_id=finding.id,
        changes={"status": finding.status, "contract_id": str(finding.contract_id)},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(finding)
    return _risk_out(finding)


# --------------------------------------------------------------------------
# Комментарии (роль «Наблюдатель», ТЗ раздел 7)
# --------------------------------------------------------------------------


@router.get("/contracts/{contract_id}/comments", response_model=list[CommentOut])
async def list_comments(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contract = await get_visible_contract(contract_id, user, db)
    rows = (
        (
            await db.execute(
                select(DocumentComment, Clause.anchor)
                .join(Clause, Clause.id == DocumentComment.clause_id, isouter=True)
                .where(DocumentComment.contract_id == contract.id)
                .order_by(DocumentComment.created_at)
            )
        )
        .all()
    )
    return [
        CommentOut(**{**_row_dict(comment), "clause_anchor": anchor})
        for comment, anchor in rows
    ]


@router.post(
    "/contracts/{contract_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    contract_id: uuid.UUID,
    data: CommentCreate,
    request: Request,
    user: User = Depends(require_permission("comment")),
    db: AsyncSession = Depends(get_db),
):
    """Комментарий к документу или пункту. Статусы при этом не меняются."""
    contract = await get_visible_contract(contract_id, user, db)
    text = (data.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Комментарий пустой")

    anchor = None
    if data.clause_id is not None:
        clause = await db.get(Clause, data.clause_id)
        if clause is None or clause.contract_id != contract.id:
            raise HTTPException(status_code=404, detail="Пункт не найден")
        anchor = clause.anchor

    comment = DocumentComment(
        contract_id=contract.id,
        clause_id=data.clause_id,
        text=text,
        author_id=user.id,
        author_name=user.full_name or user.username,
        author_role=user.role,
    )
    db.add(comment)
    await log_action(
        db,
        action="comment_added",
        user_id=user.id,
        resource_type="contract",
        resource_id=contract.id,
        changes={"clause_anchor": anchor},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(comment)
    return CommentOut(**{**_row_dict(comment), "clause_anchor": anchor})


@router.patch("/comments/{comment_id}/resolve", response_model=CommentOut)
async def resolve_comment(
    comment_id: uuid.UUID,
    user: User = Depends(require_permission("comment")),
    db: AsyncSession = Depends(get_db),
):
    comment = await db.get(DocumentComment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Комментарий не найден")
    await get_visible_contract(comment.contract_id, user, db)
    comment.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(comment)
    return CommentOut(**{**_row_dict(comment), "clause_anchor": None})


# --------------------------------------------------------------------------
# Внутреннее
# --------------------------------------------------------------------------


async def _clause_list_payload(
    db: AsyncSession, contract: Contract, stored: list[Clause]
) -> ClauseListOut:
    ids = [clause.id for clause in stored]
    checks = await clause_service.latest_checks(db, ids)
    decisions = await clause_service.current_decisions(db, ids)
    progress = await clause_service.compute_progress(db, contract.id)
    by_id = {clause.id: clause for clause in stored}

    comment_counts = dict(
        (
            await db.execute(
                select(DocumentComment.clause_id, func.count(DocumentComment.id))
                .where(DocumentComment.contract_id == contract.id)
                .group_by(DocumentComment.clause_id)
            )
        ).all()
    )

    items: list[ClauseOut] = []
    for clause in stored:
        check = checks.get(clause.id)
        decision = decisions.get(clause.id)
        parent = by_id.get(clause.parent_id) if clause.parent_id else None
        items.append(
            ClauseOut(
                id=clause.id,
                anchor=clause.anchor,
                number=clause.number,
                level=clause.level,
                title=clause.title,
                content=clause.content,
                position=clause.position,
                parent_anchor=parent.anchor if parent else None,
                check=(
                    {
                        "verdict": check.verdict,
                        "rationale": check.rationale,
                        "suggested_text": check.suggested_text,
                        "sources": check.sources or [],
                        "checked_on": check.checked_on,
                        "created_at": check.created_at,
                        # Вердикты, вынесенные до появления хеша (clause_hash
                        # is None), устаревшими не помечаем: к какой редакции
                        # они относятся, честно неизвестно.
                        "stale": bool(
                            check.clause_hash
                            and check.clause_hash != clause.content_hash
                        ),
                    }
                    if check
                    else None
                ),
                decision=(
                    _decision_out(decision, clause.content_hash) if decision else None
                ),
                comments_count=comment_counts.get(clause.id, 0),
            )
        )

    return ClauseListOut(
        contract_id=contract.id,
        status=contract.status,
        locked=is_locked(contract.status),
        progress=progress.as_dict(),
        items=items,
    )


def _decision_out(decision: ClauseDecision, current_hash: str | None) -> ClauseDecisionOut:
    return ClauseDecisionOut(
        id=decision.id,
        action=decision.action,
        comment=decision.comment,
        new_text=decision.new_text,
        decided_by=decision.decided_by,
        decided_by_name=decision.decided_by_name,
        created_at=decision.created_at,
        stale=bool(
            decision.clause_hash and current_hash and decision.clause_hash != current_hash
        ),
    )


def _apply_resolution(finding, data: FindingResolveIn, user: User) -> None:
    new_status = (data.status or "").strip().lower()
    if new_status not in FINDING_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый статус. Допустимы: {', '.join(sorted(FINDING_STATUSES))}",
        )
    finding.status = new_status
    if hasattr(finding, "resolution_note"):
        finding.resolution_note = (data.note or "").strip() or None
    if new_status == "open":
        finding.resolved_by = None
        finding.resolved_at = None
    else:
        finding.resolved_by = user.id
        finding.resolved_at = datetime.now(timezone.utc)


def _ensure_editable(contract: Contract) -> None:
    if is_locked(contract.status):
        raise HTTPException(
            status_code=409,
            detail="Документ в финальном статусе: редактирование заблокировано",
        )


def _ensure_findings_open(contract: Contract) -> None:
    """Замечания правятся, пока документ не закрыт.

    Комментарии сюда намеренно не попадают: заметка на подписанном или
    архивном документе («расторгнут 12.03») — обычная работа, а вот отметка
    «риск устранён» после подписания переписывает историю проверки.
    """
    if is_locked(contract.status):
        raise HTTPException(
            status_code=409,
            detail=(
                "Документ закрыт: замечания по нему больше не изменяются. "
                "Запись проверки сохраняется в том виде, в каком документ "
                "подписывали."
            ),
        )


def _logic_out(row: LogicFinding) -> LogicFindingOut:
    return LogicFindingOut(
        **{
            **_row_dict(row),
            "clause_anchors": row.clause_anchors or [],
            "category_title": LOGIC_CATEGORIES.get(row.category, row.category),
        }
    )


def _risk_out(row: RiskFinding) -> RiskFindingOut:
    return RiskFindingOut(
        **{
            **_row_dict(row),
            "clause_anchors": row.clause_anchors or [],
            "category_title": RISK_CATEGORIES.get(row.category, row.category),
            "level_title": RISK_LEVELS.get(row.level, row.level),
        }
    )


def _level_order(level: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(level, 3)


def _row_dict(row) -> dict:
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
        if hasattr(row, column.name)
    }
