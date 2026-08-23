"""Детерминированные проверки Модуля 2 (ТЗ, раздел 4).

Часть расхождений внутри документа — это разметка, а не смысл: битая ссылка
«см. п. 5.4» либо разрешается в существующий пункт, либо нет. Такие проверки
считаются кодом, а не моделью: результат воспроизводим, не стоит токенов и не
может быть выдуман.

Смысловые категории (сроки, суммы, дублирование, разрывы в цепочках) остаются
за LLM — см. app/agents/logic_agent.py.
"""

from __future__ import annotations

import re

from app.services.clause_splitter import find_references

# Категории Модуля 2 из ТЗ. Ключи используются и в API, и на фронте.
LOGIC_CATEGORIES: dict[str, str] = {
    "deadlines": "Противоречия по срокам",
    "amounts": "Противоречия по суммам",
    "broken_refs": "Битые перекрёстные ссылки",
    "undefined_terms": "Неопределённые термины",
    "duplication": "Дублирование",
    "chain_gaps": "Разрывы в цепочках",
    "party_naming": "Несогласованность сторон",
}

# Категории, которые ищет модель; остальные считаются кодом.
AI_CATEGORIES = ("deadlines", "amounts", "duplication", "chain_gaps")

# Обозначения сторон, встречающиеся в договорах РУз.
PARTY_WORDS = [
    "Поставщик",
    "Покупатель",
    "Заказчик",
    "Исполнитель",
    "Подрядчик",
    "Арендодатель",
    "Арендатор",
    "Продавец",
    "Клиент",
    "Работник",
    "Работодатель",
    "Лицензиар",
    "Лицензиат",
    "Принципал",
    "Агент",
    "Кредитор",
    "Должник",
]

# «именуемое в дальнейшем «Поставщик»» — так стороны определяются в шапке.
RE_PARTY_DEFINITION = re.compile(
    r"именуем\w*(?:\s+в\s+дальнейшем)?\s*[«\"']([А-ЯЁ][а-яёА-ЯЁ\- ]{2,40})[»\"']",
    re.IGNORECASE,
)

# Термин в кавычках с заглавной буквы: «Товар», «Спецификация».
RE_QUOTED_TERM = re.compile(r"[«\"]([А-ЯЁ][а-яёА-ЯЁ\- ]{2,40})[»\"]")

RE_DEFINITIONS_HEADING = re.compile(
    r"(термин|определени|понятия)", re.IGNORECASE
)


def detect_broken_references(clauses: list) -> list[dict]:
    """Ссылки на пункты, которых в документе нет."""
    anchors = {clause.anchor for clause in clauses}
    numbers = {clause.number for clause in clauses if clause.number}
    known = anchors | numbers
    findings: list[dict] = []

    for clause in clauses:
        # Заголовок раздела сам содержит свой номер — ссылкой это не считается.
        body = clause.content
        if clause.title and body.strip() == clause.title.strip():
            continue
        own = {clause.anchor, clause.number or clause.anchor}
        for ref in dict.fromkeys(find_references(body)):
            if ref in known or ref in own:
                continue
            # «п. 3» при наличии пункта «3.1» — ссылка на раздел, она валидна.
            if any(str(item).startswith(f"{ref}.") for item in known):
                continue
            findings.append(
                {
                    "category": "broken_refs",
                    "description": (
                        f"Пункт {clause.anchor} ссылается на пункт {ref}, "
                        f"которого в документе нет."
                    ),
                    "suggestion": (
                        f"Проверить нумерацию: заменить ссылку на существующий "
                        f"пункт или добавить пункт {ref}."
                    ),
                    "clause_anchors": [clause.anchor],
                    "detected_by": "rule",
                }
            )
    return findings


def detect_party_inconsistency(clauses: list) -> list[dict]:
    """Стороны названы в шапке одними словами, а в тексте — другими."""
    if not clauses:
        return []

    defined: set[str] = set()
    for clause in clauses[:3]:  # шапка и преамбула
        for match in RE_PARTY_DEFINITION.finditer(clause.content):
            defined.add(_canon(match.group(1)))
    if not defined:
        return []

    definition_anchor = clauses[0].anchor
    used: dict[str, list[str]] = {}
    for clause in clauses:
        for word in PARTY_WORDS:
            canon = _canon(word)
            if canon in defined:
                continue
            if re.search(rf"\b{word}\w*", clause.content):
                used.setdefault(canon, []).append(clause.anchor)

    findings: list[dict] = []
    for canon, anchors in used.items():
        findings.append(
            {
                "category": "party_naming",
                "description": (
                    f"В тексте используется обозначение «{canon.capitalize()}» "
                    f"(пункт {anchors[0]}), но в шапке стороны определены как "
                    f"{_human_list(defined)}."
                ),
                "suggestion": (
                    f"Привести обозначение к принятому в шапке или ввести "
                    f"«{canon.capitalize()}» в перечень сторон."
                ),
                "clause_anchors": [definition_anchor, *anchors[:3]],
                "detected_by": "rule",
            }
        )
    return findings


def detect_undefined_terms(clauses: list) -> list[dict]:
    """Термины в кавычках, не раскрытые в разделе определений.

    Проверка включается только когда раздел определений в документе есть:
    если его нет вовсе, это пробел договора, и его показывает Модуль 3, а не
    Модуль 2.
    """
    definition_clauses = [
        clause
        for clause in clauses
        if clause.title and RE_DEFINITIONS_HEADING.search(clause.title)
    ]
    if not definition_clauses:
        return []

    defined: set[str] = set()
    definition_anchors: list[str] = []
    for clause in definition_clauses:
        definition_anchors.append(clause.anchor)
        defined |= {_canon(m) for m in RE_QUOTED_TERM.findall(clause.content)}
        for child in clauses:
            if child.parent_id and child.parent_id == clause.id:
                definition_anchors.append(child.anchor)
                defined |= {_canon(m) for m in RE_QUOTED_TERM.findall(child.content)}
    for clause in clauses[:3]:
        defined |= {_canon(m) for m in RE_PARTY_DEFINITION.findall(clause.content)}

    usage: dict[str, list[str]] = {}
    for clause in clauses:
        if clause.anchor in definition_anchors:
            continue
        for term in RE_QUOTED_TERM.findall(clause.content):
            canon = _canon(term)
            if canon in defined or canon in {_canon(w) for w in PARTY_WORDS}:
                continue
            usage.setdefault(canon, []).append(clause.anchor)

    findings: list[dict] = []
    for canon, anchors in usage.items():
        # Разовое употребление — чаще всего название организации, а не термин.
        if len(anchors) < 2:
            continue
        findings.append(
            {
                "category": "undefined_terms",
                "description": (
                    f"Термин «{canon.capitalize()}» используется в пунктах "
                    f"{', '.join(anchors[:4])}, но не раскрыт в разделе определений."
                ),
                "suggestion": (
                    f"Добавить определение термина «{canon.capitalize()}» "
                    f"в раздел определений."
                ),
                "clause_anchors": [definition_anchors[0], *anchors[:3]],
                "detected_by": "rule",
            }
        )
    return findings


def run_rule_checks(clauses: list) -> list[dict]:
    return [
        *detect_broken_references(clauses),
        *detect_party_inconsistency(clauses),
        *detect_undefined_terms(clauses),
    ]


def _canon(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _human_list(values) -> str:
    return ", ".join(f"«{value.capitalize()}»" for value in sorted(values))
