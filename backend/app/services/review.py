"""Запуск модулей проверки и сборка сводки (ТЗ, раздел 4 и 5).

Модули запускаются по отдельности или все сразу. Каждый запуск — строка
review_runs со своим статусом, поэтому прогресс переживает перезапуск сервера,
а юрист видит, какой именно модуль отработал.

Статусы документа ведёт этот модуль, а не интерфейс:
  запустили модули            -> «На проверке»
  все три модуля отработали   -> «Проверен»
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.clause_checker import (
    BATCH_SIZE,
    ClauseCheckerAgent,
    build_query,
)
from app.agents.logic_agent import LogicAgent
from app.agents.risk_agent import RISK_CATEGORIES, RISK_LEVELS, RiskAgent
from app.db.models import (
    Clause,
    ClauseCheck,
    ClauseVerdict,
    Contract,
    ContractStatus,
    LogicFinding,
    ReviewModule,
    ReviewRun,
    RiskFinding,
    User,
)
from app.services import clauses as clause_service
from app.services.ai_usage import record_ai_usage
from app.services.legal_search import format_legal_context, search_legal_articles
from app.services.logic_check import LOGIC_CATEGORIES, run_rule_checks
from app.utils.audit import log_action
from app.utils.llm import UsageCollector, collect_usage

logger = logging.getLogger("app.review")

ALL_MODULES = (
    ReviewModule.CLAUSES.value,
    ReviewModule.LOGIC.value,
    ReviewModule.RISKS.value,
)

MODULE_TITLES = {
    ReviewModule.CLAUSES.value: "Разбивка на пункты и сверка с правовой базой",
    ReviewModule.LOGIC.value: "Сверка логики между пунктами",
    ReviewModule.RISKS.value: "Сверка на смысл и риски",
}


class ReviewError(Exception):
    """Ошибка запуска модуля, понятная пользователю."""


async def has_running_review(db: AsyncSession, contract_id: uuid.UUID) -> bool:
    """Идёт ли сейчас проверка по документу.

    Пока прогон работает, текст документа править нельзя: пересборка пунктов
    удаляет строки, на которые фоновая задача уже ссылается, и прогон падает
    на нарушении внешнего ключа.
    """
    return bool(
        (
            await db.execute(
                select(func.count(ReviewRun.id)).where(
                    ReviewRun.contract_id == contract_id,
                    ReviewRun.status == "running",
                )
            )
        ).scalar_one()
    )


async def create_runs(
    db: AsyncSession,
    contract: Contract,
    user: User,
    modules: list[str],
    *,
    party_side: str | None = None,
) -> list[ReviewRun]:
    """Создаёт прогоны и переводит документ в статус «На проверке»."""
    unknown = [module for module in modules if module not in ALL_MODULES]
    if unknown:
        raise ReviewError(f"Неизвестный модуль проверки: {', '.join(unknown)}")
    if not contract.content or not contract.content.strip():
        raise ReviewError("У документа нет текста для проверки")
    if ReviewModule.RISKS.value in modules and not (party_side or "").strip():
        # Требование ТЗ: сторона меняет всю оптику анализа, без неё результат
        # Модуля 3 не имеет смысла.
        raise ReviewError(
            "Для модуля «Смысл и риски» укажите, чью сторону вы представляете"
        )

    # ТЗ: «документ автоматически делится на структурные единицы». Делаем это
    # здесь, до запуска модулей: иначе три параллельных прогона разбирали бы
    # документ каждый в своей сессии и конфликтовали на уникальном якоре пункта.
    stored = await clause_service.get_clauses(db, contract.id)
    if not stored:
        await clause_service.rebuild_clauses(db, contract)

    already = set(
        (
            await db.execute(
                select(ReviewRun.module).where(
                    ReviewRun.contract_id == contract.id,
                    ReviewRun.status == "running",
                    ReviewRun.module.in_(modules),
                )
            )
        )
        .scalars()
        .all()
    )
    if already:
        # Двойной клик или ретрай сети создавал второй прогон того же модуля:
        # оба удаляли открытые находки и вставляли свои, юрист видел задвоенный
        # список замечаний.
        raise ReviewError(
            "Проверка уже идёт: "
            + ", ".join(MODULE_TITLES[module] for module in sorted(already))
        )

    runs: list[ReviewRun] = []
    for module in modules:
        run = ReviewRun(
            contract_id=contract.id,
            module=module,
            status="running",
            party_side=party_side.strip() if party_side else None,
            started_by=user.id,
        )
        db.add(run)
        runs.append(run)

    if contract.status in {
        ContractStatus.DRAFT.value,
        ContractStatus.GENERATED.value,
        ContractStatus.ANALYZED.value,
        ContractStatus.NEEDS_REVISION.value,
    }:
        contract.status = ContractStatus.ANALYZING.value

    await log_action(
        db,
        action="review_started",
        user_id=user.id,
        resource_type="contract",
        resource_id=contract.id,
        changes={"modules": modules, "party_side": party_side},
    )
    await db.flush()
    return runs


async def perform_run(
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Выполняет один прогон в собственной сессии (фоновая задача)."""
    async with session_factory() as db:
        run = await db.get(ReviewRun, run_id)
        if run is None:
            return
        contract = await db.get(Contract, run.contract_id)
        user = await db.get(User, user_id)
        if contract is None or user is None:
            run.status = "failed"
            run.error = "Документ или пользователь не найдены"
            run.finished_at = _now()
            await db.commit()
            return

        usage = UsageCollector()
        try:
            with collect_usage() as usage:
                if run.module == ReviewModule.CLAUSES.value:
                    await _run_clauses(db, contract, run)
                elif run.module == ReviewModule.LOGIC.value:
                    await _run_logic(db, contract, run)
                else:
                    await _run_risks(db, contract, run)
            record_ai_usage(
                db, user, usage, endpoint="review", agent=f"module_{run.module}"
            )
            run.status = "done"
            # Модуль мог отработать частично (например, правила Модуля 2
            # сработали, а модель — нет) и оставить предупреждение: затирать
            # его нельзя, иначе юрист снова решит, что проверен весь документ.
        except Exception as exc:  # noqa: BLE001 - причина уходит юристу в UI
            logger.exception("Review run %s (%s) failed", run_id, run.module)
            reason = _safe_reason(exc)
            # Токены, потраченные до сбоя, — это реальные деньги организации.
            # Раньше учёт писался только в ветке успеха: упавший на середине
            # прогон жёг квоту, не приближая её к дневному лимиту, и повторы
            # на «трудном» договоре обходились вдвойне.
            spent = usage
            # Сессия после неудачного flush в aborted-состоянии: любой SELECT
            # по ней бросит PendingRollbackError, и статус прогона так и не
            # сохранится — документ навсегда зависнет в «На проверке».
            await db.rollback()
            run = await db.get(ReviewRun, run_id)
            contract = await db.get(Contract, run.contract_id) if run else None
            if run is None:
                return
            run.status = "failed"
            run.error = str(reason)[:500]
            user = await db.get(User, user_id)
            if user is not None and (spent.input_tokens or spent.output_tokens):
                record_ai_usage(
                    db,
                    user,
                    spent,
                    endpoint="review",
                    agent=f"module_{run.module}",
                )

        run.finished_at = _now()
        if contract is not None:
            await _sync_contract_status(db, contract)
        await db.commit()


# --------------------------------------------------------------------------
# Модуль 1
# --------------------------------------------------------------------------


async def _run_clauses(db: AsyncSession, contract: Contract, run: ReviewRun) -> None:
    stored = await clause_service.get_clauses(db, contract.id)
    run.clauses_total = len(stored)
    if not stored:
        return

    # Модули 2 и 3 перед вставкой чистят прежние открытые находки, а Модуль 1
    # этого не делал: каждый повторный прогон добавлял ещё по вердикту на
    # пункт, и выборка «последнего вердикта» тянула из БД всю историю. Актуален
    # всегда последний прогон, поэтому прежние вердикты по этим пунктам
    # удаляем.
    await db.execute(
        delete(ClauseCheck).where(ClauseCheck.clause_id.in_([c.id for c in stored]))
    )
    await db.flush()

    agent = ClauseCheckerAgent()
    checked = 0

    for batch in _batched(stored, BATCH_SIZE):
        payload = [
            {
                "anchor": clause.anchor,
                "number": clause.number,
                "title": clause.title,
                "content": clause.content,
            }
            for clause in batch
        ]
        # Заголовок раздела правовой нагрузки не несёт: тратить на него запрос
        # к модели и место в отчёте незачем.
        headings = [clause for clause in batch if _is_heading(clause)]
        checkable = [
            item
            for item in payload
            if item["anchor"] not in {clause.anchor for clause in headings}
        ]

        for clause in headings:
            db.add(
                ClauseCheck(
                    clause_id=clause.id,
                    run_id=run.id,
                    verdict=ClauseVerdict.NO_NORM.value,
                    rationale="Заголовок раздела: самостоятельного условия не содержит.",
                    sources=[],
                    clause_hash=clause.content_hash,
                )
            )
            checked += 1

        if not checkable:
            continue

        sources = await search_legal_articles(
            db, q=build_query(checkable, contract.contract_type), limit=8
        )
        verdicts = await agent.check_batch(
            checkable,
            sources,
            doc_type=contract.contract_type,
            laws_block=format_legal_context(sources, max_chars=10_000),
        )
        by_anchor = {clause.anchor: clause for clause in batch}
        for verdict in verdicts:
            clause = by_anchor.get(verdict["anchor"])
            if clause is None:
                continue
            db.add(
                ClauseCheck(
                    clause_id=clause.id,
                    run_id=run.id,
                    verdict=verdict["verdict"],
                    rationale=verdict.get("rationale"),
                    suggested_text=verdict.get("suggested_text"),
                    sources=verdict.get("sources") or [],
                    clause_hash=clause.content_hash,
                )
            )
            checked += 1

    run.findings_total = checked
    await db.flush()


# --------------------------------------------------------------------------
# Модуль 2
# --------------------------------------------------------------------------


async def _run_logic(db: AsyncSession, contract: Contract, run: ReviewRun) -> None:
    stored = await clause_service.get_clauses(db, contract.id)
    run.clauses_total = len(stored)
    if len(stored) < 2:
        return

    # Открытые находки прошлого прогона заменяем: документ мог измениться.
    # Разобранные юристом (принятые/отклонённые) остаются как история решений.
    await db.execute(
        delete(LogicFinding).where(
            LogicFinding.contract_id == contract.id,
            LogicFinding.status == "open",
        )
    )

    findings = run_rule_checks(stored)
    try:
        payload = [
            {"anchor": c.anchor, "title": c.title, "content": c.content}
            for c in stored
        ]
        findings += await LogicAgent().find_conflicts(payload)
    except Exception:  # noqa: BLE001 — детерминированная часть уже дала результат
        # Детерминированная часть Модуля 2 обязана работать и без LLM: битые
        # ссылки юрист должен увидеть даже когда AI недоступен.
        logger.exception("Logic agent failed for contract %s", contract.id)
        if not findings:
            raise
        # Но и молчать нельзя: юрист видел «Отработал» и считал, что документ
        # проверен целиком, хотя получил только правила. Прогон остаётся
        # успешным — детерминированная часть отработала, — а факт сбоя
        # записывается, чтобы интерфейс показал предупреждение.
        run.error = (
            "Правила отработали, но проверка логики моделью не удалась. "
            "Запустите модуль ещё раз, чтобы получить полный результат."
        )

    for finding in findings:
        db.add(
            LogicFinding(
                contract_id=contract.id,
                run_id=run.id,
                category=finding["category"],
                description=finding["description"],
                suggestion=finding.get("suggestion"),
                clause_anchors=finding.get("clause_anchors") or [],
                detected_by=finding.get("detected_by", "rule"),
            )
        )
    run.findings_total = len(findings)
    await db.flush()


# --------------------------------------------------------------------------
# Модуль 3
# --------------------------------------------------------------------------


async def _run_risks(db: AsyncSession, contract: Contract, run: ReviewRun) -> None:
    stored = await clause_service.get_clauses(db, contract.id)
    run.clauses_total = len(stored)

    await db.execute(
        delete(RiskFinding).where(
            RiskFinding.contract_id == contract.id,
            RiskFinding.status == "open",
        )
    )

    payload = [
        {"anchor": c.anchor, "title": c.title, "content": c.content} for c in stored
    ]
    result = await RiskAgent().assess_positioned(
        payload,
        party_side=run.party_side or "",
        doc_type=contract.contract_type,
    )
    for risk in result["risks"]:
        db.add(
            RiskFinding(
                contract_id=contract.id,
                run_id=run.id,
                category=risk["category"],
                level=risk["level"],
                description=risk["description"],
                consequence=risk.get("consequence"),
                mitigation=risk.get("mitigation"),
                clause_anchors=risk.get("clause_anchors") or [],
            )
        )
    run.findings_total = len(result["risks"])
    run.summary = (result.get("summary") or "").strip() or None
    contract.risk_score = result["overall_score"]
    await db.flush()


# --------------------------------------------------------------------------
# Статус и сводка
# --------------------------------------------------------------------------


def _safe_reason(exc: BaseException) -> str:
    """Что из ошибки можно показать юристу и записать в БД.

    `str(exc)` показывать нельзя: у ошибки SQLAlchemy внутри лежит текст
    запроса вместе с параметрами, то есть куски договора, а колонка
    `review_runs.error` видна на экране. Наружу идут только наши собственные
    формулировки, всё остальное — в лог.
    """
    detail = getattr(exc, "detail", None)
    if isinstance(detail, str) and detail:
        return detail
    if isinstance(exc, (ReviewError, ValueError)):
        return str(exc) or "Ошибка проверки"
    return "Внутренняя ошибка проверки. Попробуйте запустить модуль ещё раз."


async def _sync_contract_status(db: AsyncSession, contract: Contract) -> None:
    """Снимает «На проверке», когда работающих прогонов не осталось.

    «Проверен» ставится, если отработал хотя бы один модуль: ТЗ разрешает
    гонять их по отдельности. Если же упали все — документ возвращается в
    «Черновик», иначе он навсегда застревает в «На проверке».

    Блокировка строки договора здесь обязательна. Каждый модуль работает в
    своей сессии, а собственный `status="done"` к моменту подсчёта ещё не
    закоммичен. Без блокировки три прогона, финиширующие в одном окне, видят
    друг друга как «running» — и ни один не снимает «На проверке». Документ
    остаётся в нём навсегда: подтвердить его из этого статуса нельзя, и
    чинится это только руками в БД. Под блокировкой прогоны выстраиваются в
    очередь, и последний видит остальных уже завершёнными.
    """
    if contract.status != ContractStatus.ANALYZING.value:
        return
    locked = (
        await db.execute(
            select(Contract)
            .where(Contract.id == contract.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    # Пока ждали блокировку, статус мог сменить кто-то другой.
    if locked is None or locked.status != ContractStatus.ANALYZING.value:
        return
    contract = locked
    running = (
        await db.execute(
            select(func.count(ReviewRun.id)).where(
                ReviewRun.contract_id == contract.id,
                ReviewRun.status == "running",
            )
        )
    ).scalar_one()
    if running:
        return
    # ТЗ разрешает запускать модули по отдельности, поэтому «Проверен»
    # ставится по завершении запущенного набора, а не обязательно всех трёх.
    # Иначе юрист, прогнавший только Модуль 1 и прошедший все пункты, упирался
    # в «Действие недоступно из статуса analyzing» без выхода, кроме возврата
    # на доработку.
    finished = (
        await db.execute(
            select(func.count(ReviewRun.id)).where(
                ReviewRun.contract_id == contract.id,
                ReviewRun.status == "done",
            )
        )
    ).scalar_one()
    if finished:
        contract.status = ContractStatus.ANALYZED.value
        return
    # Все запущенные прогоны упали — проверки не было, и «Проверен» ставить
    # нельзя. Но и оставлять «На проверке» нельзя: ничего уже не идёт, а
    # подтверждение из этого статуса запрещено, и документ чинится только
    # руками в базе. Возвращаем в «Черновик», откуда проверку можно запустить
    # заново. Пометка «Сгенерирован» при этом теряется — это осознанный размен
    # происхождения документа на его работоспособность.
    contract.status = ContractStatus.DRAFT.value


async def latest_runs(db: AsyncSession, contract_id: uuid.UUID) -> dict[str, ReviewRun]:
    rows = (
        (
            await db.execute(
                select(ReviewRun)
                .where(ReviewRun.contract_id == contract_id)
                .order_by(ReviewRun.started_at)
            )
        )
        .scalars()
        .all()
    )
    return {run.module: run for run in rows}


async def summary(db: AsyncSession, contract: Contract) -> dict:
    """Сводка по документу (ТЗ, раздел 5).

    Сколько пунктов проверено, сколько замечаний по каждому модулю, сколько
    устранено и что осталось.
    """
    progress = await clause_service.compute_progress(db, contract.id)
    runs = await latest_runs(db, contract.id)

    verdicts = dict.fromkeys((v.value for v in ClauseVerdict), 0)
    stored = await clause_service.get_clauses(db, contract.id)
    checks = await clause_service.latest_checks(db, [c.id for c in stored])
    for check in checks.values():
        verdicts[check.verdict] = verdicts.get(check.verdict, 0) + 1

    logic_rows = (
        (
            await db.execute(
                select(LogicFinding.category, LogicFinding.status).where(
                    LogicFinding.contract_id == contract.id
                )
            )
        )
        .all()
    )
    risk_rows = (
        (
            await db.execute(
                select(RiskFinding.category, RiskFinding.level, RiskFinding.status).where(
                    RiskFinding.contract_id == contract.id
                )
            )
        )
        .all()
    )

    return {
        "contract_id": str(contract.id),
        "status": contract.status,
        "clauses": {
            **progress.as_dict(),
            "checked": len(checks),
            "verdicts": verdicts,
        },
        "logic": {
            "total": len(logic_rows),
            "open": sum(1 for _, status in logic_rows if status == "open"),
            "resolved": sum(1 for _, status in logic_rows if status != "open"),
            "by_category": {
                key: sum(1 for category, _ in logic_rows if category == key)
                for key in LOGIC_CATEGORIES
            },
        },
        "risks": {
            "total": len(risk_rows),
            "open": sum(1 for _, _, status in risk_rows if status == "open"),
            "resolved": sum(1 for _, _, status in risk_rows if status != "open"),
            "by_level": {
                key: sum(1 for _, level, _ in risk_rows if level == key)
                for key in RISK_LEVELS
            },
            "by_category": {
                key: sum(1 for category, _, _ in risk_rows if category == key)
                for key in RISK_CATEGORIES
            },
            "score": contract.risk_score,
            # Что критично поправить до подписания — резюме Модуля 3 (ТЗ, 4).
            "summary": (
                runs[ReviewModule.RISKS.value].summary
                if ReviewModule.RISKS.value in runs
                else None
            ),
        },
        "modules": [
            {
                "module": module,
                "title": MODULE_TITLES[module],
                "status": runs[module].status if module in runs else "not_started",
                "party_side": runs[module].party_side if module in runs else None,
                "findings_total": runs[module].findings_total if module in runs else 0,
                "summary": runs[module].summary if module in runs else None,
                "error": runs[module].error if module in runs else None,
                "finished_at": (
                    runs[module].finished_at.isoformat()
                    if module in runs and runs[module].finished_at
                    else None
                ),
            }
            for module in ALL_MODULES
        ],
    }


def _is_heading(clause: Clause) -> bool:
    if not clause.title:
        return False
    return clause.content.strip() == clause.title.strip()


def _batched(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _now() -> datetime:
    return datetime.now(timezone.utc)
