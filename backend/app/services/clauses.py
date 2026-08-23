"""Хранение пунктов документа и прогресс подтверждения (ТЗ, раздел 4).

Ключевое правило ТЗ: пока не подтверждены все пункты, документ не может
перейти в статус «Подтверждён юристом». Проверка живёт здесь и вызывается из
workflow — не из интерфейса.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Clause,
    ClauseCheck,
    ClauseDecision,
    ClauseDecisionAction,
    Contract,
)
from app.services import clause_splitter


@dataclass
class Progress:
    """Счётчик «N из M подтверждено» для панели документа."""

    total: int = 0
    confirmed: int = 0
    edited: int = 0
    deferred: int = 0
    commented: int = 0
    untouched: int = 0
    stale: int = 0  # решение есть, но текст пункта после него менялся

    @property
    def resolved(self) -> int:
        """Пункты, по которым юрист принял решение «принято как есть»."""
        return self.confirmed + self.edited

    @property
    def complete(self) -> bool:
        return self.total > 0 and self.resolved == self.total

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "confirmed": self.confirmed,
            "edited": self.edited,
            "deferred": self.deferred,
            "commented": self.commented,
            "untouched": self.untouched,
            "stale": self.stale,
            "resolved": self.resolved,
            "complete": self.complete,
        }


async def rebuild_clauses(
    db: AsyncSession, contract: Contract, *, keep_decisions: bool = True
) -> list[Clause]:
    """Пересобирает дерево пунктов из текста документа.

    Решения юриста и вердикты Модуля 1 переносятся по якорю пункта: если текст
    пункта не изменился, подтверждение и вердикт продолжают действовать. Если
    изменился — решение остаётся в истории и помечается неактуальным, вердикт
    помечается устаревшим, и юрист проходит по пункту заново. Так правка
    одного пункта не обнуляет работу по всему договору.

    Вердикты раньше не переносились вовсе: дерево удаляется целиком, а
    `clause_checks` висят на пункте каскадом. Правка одного пункта стирала
    результат сверки по всему документу, и Модуль 1 приходилось гонять заново
    за счёт дневной квоты токенов организации.
    """
    # Границы пунктов считаются по нормализованному тексту, поэтому и в
    # документе держим его же. Нормализация идемпотентна и трогает только
    # оформление: хвостовые пробелы, повторы пробелов, мягкие переносы и
    # разрыв слова дефисом после OCR.
    normalized = clause_splitter.normalize(contract.content or "")
    if normalized != (contract.content or ""):
        contract.content = normalized
    parsed = clause_splitter.split_document(normalized)

    previous: dict[str, tuple[uuid.UUID, str]] = {}
    if keep_decisions:
        rows = (
            await db.execute(
                select(Clause.anchor, Clause.id, Clause.content_hash).where(
                    Clause.contract_id == contract.id
                )
            )
        ).all()
        previous = {anchor: (cid, chash) for anchor, cid, chash in rows}

    carried: dict[str, list[ClauseDecision]] = {}
    carried_checks: dict[str, list[ClauseCheck]] = {}
    if previous:
        old_ids = [cid for cid, _ in previous.values()]
        decisions = (
            (
                await db.execute(
                    select(ClauseDecision)
                    .where(ClauseDecision.clause_id.in_(old_ids))
                    .order_by(ClauseDecision.created_at)
                )
            )
            .scalars()
            .all()
        )
        by_old_id: dict[uuid.UUID, str] = {
            cid: anchor for anchor, (cid, _) in previous.items()
        }
        for decision in decisions:
            anchor = by_old_id.get(decision.clause_id)
            if anchor:
                carried.setdefault(anchor, []).append(decision)

        checks = (
            (
                await db.execute(
                    select(ClauseCheck)
                    .where(ClauseCheck.clause_id.in_(old_ids))
                    .order_by(ClauseCheck.created_at)
                )
            )
            .scalars()
            .all()
        )
        for check in checks:
            anchor = by_old_id.get(check.clause_id)
            if anchor:
                carried_checks.setdefault(anchor, []).append(check)

    # Старое дерево удаляем целиком: якоря могли поменяться местами, а
    # частичная синхронизация давала бы пункты-призраки.
    await db.execute(delete(Clause).where(Clause.contract_id == contract.id))
    await db.flush()

    created: dict[str, Clause] = {}
    for item in parsed:
        clause = Clause(
            contract_id=contract.id,
            parent_id=None,
            anchor=item.anchor,
            number=item.number,
            level=item.level,
            title=item.title,
            content=item.content,
            content_hash=item.content_hash,
            position=item.position,
            start_offset=item.start_offset,
            end_offset=item.end_offset,
        )
        db.add(clause)
        created[item.anchor] = clause
    await db.flush()

    for item in parsed:
        if item.parent_anchor and item.parent_anchor in created:
            created[item.anchor].parent_id = created[item.parent_anchor].id

    for anchor, decisions in carried.items():
        clause = created.get(anchor)
        if clause is None:
            continue
        for decision in decisions:
            # Актуальность решения НЕ гасим по смене текста: устаревание
            # определяется сравнением хешей в compute_progress. Если снять
            # is_current здесь, решение исчезнет из выборки актуальных, и
            # пункт покажется просто непройденным — юрист потеряет сигнал
            # «вы это уже подтверждали, текст переписали, проверьте заново».
            db.add(
                ClauseDecision(
                    clause_id=clause.id,
                    action=decision.action,
                    comment=decision.comment,
                    previous_text=decision.previous_text,
                    new_text=decision.new_text,
                    clause_hash=decision.clause_hash,
                    is_current=decision.is_current,
                    decided_by=decision.decided_by,
                    decided_by_name=decision.decided_by_name,
                    created_at=decision.created_at,
                )
            )

    for anchor, checks in carried_checks.items():
        clause = created.get(anchor)
        if clause is None:
            continue
        for check in checks:
            # clause_hash переносится как есть: по нему видно, к какой редакции
            # пункта вердикт относится. Совпал с новым — вердикт действует, не
            # совпал — помечается устаревшим при выдаче.
            db.add(
                ClauseCheck(
                    clause_id=clause.id,
                    run_id=check.run_id,
                    verdict=check.verdict,
                    rationale=check.rationale,
                    suggested_text=check.suggested_text,
                    sources=check.sources,
                    checked_on=check.checked_on,
                    clause_hash=check.clause_hash,
                    created_at=check.created_at,
                )
            )

    await db.flush()
    return list(created.values())


async def get_clauses(db: AsyncSession, contract_id: uuid.UUID) -> list[Clause]:
    result = await db.execute(
        select(Clause)
        .where(Clause.contract_id == contract_id)
        .order_by(Clause.position)
    )
    return list(result.scalars().all())


async def latest_checks(
    db: AsyncSession, clause_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ClauseCheck]:
    """Последняя сверка по каждому пункту."""
    if not clause_ids:
        return {}
    rows = (
        (
            await db.execute(
                select(ClauseCheck)
                .where(ClauseCheck.clause_id.in_(clause_ids))
                .order_by(ClauseCheck.created_at)
            )
        )
        .scalars()
        .all()
    )
    return {check.clause_id: check for check in rows}


async def current_decisions(
    db: AsyncSession, clause_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ClauseDecision]:
    """Актуальное решение юриста по каждому пункту."""
    if not clause_ids:
        return {}
    rows = (
        (
            await db.execute(
                select(ClauseDecision)
                .where(
                    ClauseDecision.clause_id.in_(clause_ids),
                    ClauseDecision.is_current.is_(True),
                )
                .order_by(ClauseDecision.created_at)
            )
        )
        .scalars()
        .all()
    )
    return {decision.clause_id: decision for decision in rows}


async def compute_progress(db: AsyncSession, contract_id: uuid.UUID) -> Progress:
    """Считает прогресс прохода по пунктам.

    Устаревшим считается решение, принятое по другой редакции пункта: текст
    поменяли после подтверждения, значит подтверждение больше не действует.
    """
    clauses = await get_clauses(db, contract_id)
    progress = Progress(total=len(clauses))
    if not clauses:
        return progress

    decisions = await current_decisions(db, [clause.id for clause in clauses])
    hashes = {clause.id: clause.content_hash for clause in clauses}

    for clause in clauses:
        decision = decisions.get(clause.id)
        if decision is None:
            progress.untouched += 1
            continue
        if decision.clause_hash and decision.clause_hash != hashes[clause.id]:
            progress.stale += 1
            progress.untouched += 1
            continue
        if decision.action == ClauseDecisionAction.CONFIRM.value:
            progress.confirmed += 1
        elif decision.action == ClauseDecisionAction.EDIT.value:
            progress.edited += 1
        elif decision.action == ClauseDecisionAction.DEFER.value:
            progress.deferred += 1
        elif decision.action == ClauseDecisionAction.COMMENT.value:
            progress.commented += 1
            progress.untouched += 1
    return progress


def apply_clause_edit(content: str, clause: Clause, new_text: str) -> str:
    """Вставляет новую редакцию пункта на его место в тексте документа.

    Именно вставка по границам, а не пересборка документа из пунктов: только
    так сохраняются слово «Раздел», римская нумерация и маркеры подпунктов,
    которых в самих пунктах нет.
    """
    prefix = ""
    if clause.number:
        prefix = f"{clause.number}. "
    elif not clause.anchor.startswith(("§", "преамбула")) and "." in clause.anchor:
        # Подпункт «1.2.а» — в тексте он помечен как «а)».
        prefix = f"{clause.anchor.rsplit('.', 1)[-1]}) "

    start, end = clause.start_offset, clause.end_offset
    if not (0 <= start < end <= len(content)):
        # Границы разъехались с текстом — безопаснее ничего не трогать, чем
        # вставить правку в случайное место договора.
        raise ValueError(
            "Границы пункта не соответствуют тексту документа. "
            "Пересоберите пункты и повторите правку."
        )

    tail = content[end:]
    separator = "" if not tail or tail.startswith("\n") else "\n"
    return content[:start] + prefix + new_text.strip() + separator + tail
