"""Каталог отметок («плашек») на документах и права на их простановку.

Единственное место, где описан состав плашек: чтобы добавить/переименовать
отметку, правится только этот файл (и его зеркало на фронте — lib/labels.ts).

Отметки живут параллельно статусу договора: на одном документе одновременно
может висеть «Проверено ИИ», «Подготовлено» и «Утверждено».
"""

from app.db.models import Role

# Тон плашки для фронта: info | neutral | success | warning | danger
LABEL_CATALOGUE: dict[str, dict] = {
    "ai_reviewed": {
        "title": "Проверено ИИ",
        "tone": "info",
        # Ставится автоматически после анализа агентами, руками — нельзя.
        "auto_only": True,
        "permission": None,
    },
    "prepared": {
        "title": "Подготовлено",
        "tone": "neutral",
        "auto_only": False,
        # Готовит документ любой, кто может его редактировать (в т.ч. юрист).
        "permission": "edit",
    },
    "approved": {
        "title": "Утверждено",
        "tone": "success",
        "auto_only": False,
        # Утверждает только тот, у кого есть право согласования.
        "permission": "approve",
    },
    "needs_revision": {
        "title": "На доработке",
        "tone": "warning",
        "auto_only": False,
        "permission": "approve",
    },
}

# Как называется должность в тексте плашки: «Утверждено · Иванов (старший юрист)»
ROLE_TITLES: dict[str, str] = {
    Role.ADMIN.value: "администратор",
    Role.HEAD.value: "руководитель отдела",
    Role.SENIOR_LAWYER.value: "старший юрист",
    Role.LAWYER.value: "юрист",
    Role.COMPLIANCE.value: "комплаенс",
    Role.FINANCE.value: "финансист",
    Role.EXTERNAL.value: "внешний пользователь",
}

# Человеческие названия агентов для плашки «Проверено ИИ»
AGENT_TITLES: dict[str, str] = {
    "contract_analyzer": "Анализатор договора",
    "law_agent": "Правовой агент",
    "risk_agent": "Риск-агент",
    "compliance_agent": "Комплаенс-агент",
    "draft_agent": "Агент-черновик",
    "translation_agent": "Переводчик",
    "due_diligence": "Legal Due Diligence",
}


def is_known_label(kind: str) -> bool:
    return kind in LABEL_CATALOGUE


def label_permission(kind: str) -> str | None:
    """Право, необходимое для ручной простановки отметки."""
    return LABEL_CATALOGUE.get(kind, {}).get("permission")


def is_auto_only(kind: str) -> bool:
    """Отметка ставится только автоматически (агентом), руками нельзя."""
    return bool(LABEL_CATALOGUE.get(kind, {}).get("auto_only"))


def role_title(role: str | None) -> str | None:
    return ROLE_TITLES.get(role or "", None)


def agent_title(agent_name: str | None) -> str | None:
    if not agent_name:
        return None
    return AGENT_TITLES.get(agent_name, agent_name)
