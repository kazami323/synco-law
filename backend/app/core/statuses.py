"""Статусы документа и правила переходов (ТЗ, раздел 2).

Единственное место, где описано, как называется статус, кто его ставит и
откуда куда можно перейти. Зеркало на фронте — `STATUS_LABELS` в
frontend/src/components/contract-chips.tsx.

Важно: в ТЗ прямо указано, кто ставит каждый статус. «Система» — значит
переход выполняется кодом по факту события (сгенерировали, запустили модули,
модули отработали), а не кнопкой в интерфейсе.
"""

from app.db.models import ContractStatus

# status -> метаданные
#   title      — название в интерфейсе
#   tone       — оформление плашки: neutral | info | warning | success | danger
#   set_by     — кто ставит по ТЗ
#   locked     — редактирование текста запрещено
STATUS_CATALOGUE: dict[str, dict] = {
    ContractStatus.DRAFT.value: {
        "title": "Черновик",
        "tone": "neutral",
        "set_by": "система",
        "locked": False,
    },
    ContractStatus.GENERATED.value: {
        "title": "Сгенерирован",
        "tone": "info",
        "set_by": "система",
        "locked": False,
    },
    ContractStatus.ANALYZING.value: {
        "title": "На проверке",
        "tone": "info",
        "set_by": "система",
        "locked": False,
    },
    ContractStatus.ANALYZED.value: {
        "title": "Проверен",
        "tone": "info",
        "set_by": "система",
        "locked": False,
    },
    ContractStatus.APPROVED.value: {
        "title": "Подтверждён юристом",
        "tone": "success",
        "set_by": "юрист",
        "locked": False,
    },
    ContractStatus.NEEDS_REVISION.value: {
        "title": "На доработке",
        "tone": "warning",
        "set_by": "юрист / руководитель",
        "locked": False,
    },
    ContractStatus.APPROVED_FINANCE.value: {
        "title": "Согласован финансами",
        "tone": "success",
        "set_by": "финансы",
        "locked": False,
    },
    ContractStatus.READY_TO_SIGN.value: {
        "title": "Финальный",
        "tone": "success",
        "set_by": "руководитель отдела",
        "locked": True,
    },
    ContractStatus.SIGNED.value: {
        "title": "Подписан",
        "tone": "success",
        "set_by": "система",
        "locked": True,
    },
    ContractStatus.ARCHIVED.value: {
        "title": "В архиве",
        "tone": "neutral",
        "set_by": "юрист",
        "locked": True,
    },
}

# Права на переход в «Финальный» живут в permissions.py (право `finalize`).
# Здесь их дублировать нельзя: набор ролей уже разошёлся с матрицей прав —
# копия отдавала статус только руководителю и администратору, тогда как по
# ТЗ (раздел 7) и по permissions.py он есть и у старшего юриста.


def status_title(status: str | None) -> str:
    if not status:
        return "—"
    return STATUS_CATALOGUE.get(status, {}).get("title", status)


def is_locked(status: str | None) -> bool:
    """Редактирование текста документа запрещено."""
    if not status:
        return False
    return bool(STATUS_CATALOGUE.get(status, {}).get("locked"))


def catalogue() -> list[dict]:
    return [
        {"value": value, **meta} for value, meta in STATUS_CATALOGUE.items()
    ]
