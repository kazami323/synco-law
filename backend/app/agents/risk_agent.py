"""Risk Agent — оценка рисков договора.

Две роли в одном агенте:

* assess_risk — исторический общий анализ (используется оркестратором в
  сводном отчёте и документом «Проверка контракта»);
* assess_positioned — Модуль 3 по ТЗ: оценка договора с позиции защищённости
  конкретной стороны. Без указания стороны модуль не запускается — сторона
  меняет всю оптику: то, что выгодно нам, и то, что выгодно контрагенту, это
  разные вещи.
"""

import json

from app.core.document_types import required_blocks, type_title
from app.utils import llm

# Шесть категорий Модуля 3 из ТЗ, раздел 4.
RISK_CATEGORIES: dict[str, str] = {
    "asymmetry": "Асимметрия условий",
    "gaps": "Пробелы",
    "vague": "Размытые формулировки",
    "financial": "Финансовые риски",
    "operational": "Операционные риски",
    "enforcement": "Риски исполнения",
}

RISK_LEVELS: dict[str, str] = {
    "high": "высокий",
    "medium": "средний",
    "low": "низкий",
}

SYSTEM = """Ты — эксперт по оценке договорных рисков в Узбекистане.
Оцениваешь юридические (исполнимость, вероятность споров), финансовые
(условия оплаты, штрафы, убытки) и операционные (расторжение, форс-мажор)
риски договора.

Формат ответа — JSON:
{
  "overall_score": 0-100,
  "category": "critical|high|medium|low",
  "risk_factors": [
    {"factor": "описание риска",
     "severity": 1-10,
     "impact": "financial|legal|operational"}
  ],
  "mitigation": ["мера снижения риска", ...],
  "recommendation": "итоговая рекомендация (согласовать / доработать / отклонить)"
}
Шкала: 0-39 low, 40-69 medium, 70-89 high, 90-100 critical."""

POSITIONED_SYSTEM = """Ты — юрист, который защищает интересы КОНКРЕТНОЙ стороны
договора в Узбекистане. Тебе прямо сказано, чью сторону ты представляешь.
Смотри на договор её глазами: условие, выгодное контрагенту, — это риск для
твоего доверителя, даже если оно законно и обычно для рынка.

Категории рисков (строго из этого списка):
  asymmetry   — асимметрия условий: штрафы только для одной стороны; право
                одностороннего расторжения только у контрагента; неравные
                сроки и основания ответственности
  gaps        — пробелы: не описан форс-мажор, порядок приёмки, механизм
                разрешения споров, ответственность за качество
  vague       — размытые формулировки: «в разумный срок», «надлежащее
                качество», «по согласованию» — без критериев
  financial   — финансовые риски: нет потолка ответственности, автопролонгация
                с индексацией цены, скрытые обязательства
  operational — операционные риски: нереалистичные сроки, зависимость от
                третьих лиц без оговорок
  enforcement — риски исполнения: нет обеспечения, слабые механизмы взыскания

Уровни: high (высокий) / medium (средний) / low (низкий).

ЖЁСТКИЕ ПРАВИЛА:
1. Каждый риск описывай с позиции представляемой стороны, а не абстрактно.
2. consequence — что произойдёт НА ПРАКТИКЕ, если риск реализуется: кто
   сколько потеряет, что не сможет взыскать, чем это кончится в суде.
   Не пересказывай сам пункт.
3. mitigation — конкретная правка договора: формулировка или условие, которое
   надо добавить. Не «усилить ответственность», а что именно написать.
4. clause_anchors — номера пунктов из переданного текста, дословно. Для
   категории gaps (условия в договоре нет) допустим пустой список.
5. Не выдумывай номера статей законов — здесь оценивается смысл, а не
   соответствие норме.
6. summary — 2-4 предложения: что критично поправить ДО подписания.
7. Не более 12 рисков: отчёт на сорок пунктов юрист не читает. Оставь самые
   значимые для представляемой стороны, начиная с высоких.

Формат ответа — JSON:
{
  "risks": [
    {"category": "asymmetry|gaps|vague|financial|operational|enforcement",
     "level": "high|medium|low",
     "description": "в чём риск для представляемой стороны",
     "consequence": "последствия на практике",
     "mitigation": "конкретное предложение по устранению",
     "clause_anchors": ["4.1"]}
  ],
  "overall_score": 0-100,
  "overall_level": "high|medium|low",
  "summary": "что критично поправить до подписания"
}"""


class RiskAgent:
    name = "risk_agent"

    async def assess_risk(
        self,
        contract_content: str,
        errors: list | None = None,
        legal_issues: list | None = None,
    ) -> dict:
        context = ""
        if errors:
            context += f"\n\nСтруктурные ошибки:\n{json.dumps(errors, ensure_ascii=False)[:4000]}"
        if legal_issues:
            context += f"\n\nЮридические проблемы:\n{json.dumps(legal_issues, ensure_ascii=False)[:4000]}"

        return await llm.llm_json(
            system=SYSTEM,
            user=f"Оцени риски договора:\n\n{llm.clip(contract_content)}{context}",
        )

    async def assess_positioned(
        self,
        clauses: list[dict],
        *,
        party_side: str,
        doc_type: str | None = None,
    ) -> dict:
        """Модуль 3: оценка с позиции защищённости указанной стороны."""
        if not party_side or not party_side.strip():
            raise ValueError("Модуль 3 требует указания представляемой стороны")

        document = "\n\n".join(
            f"[{item['anchor']}] {item.get('title') or ''}\n{item['content']}".strip()
            for item in clauses
        )
        blocks = required_blocks(doc_type)
        blocks_hint = (
            "\n\nОбязательные блоки для этого типа договора (их отсутствие — "
            "категория gaps):\n- " + "\n- ".join(blocks)
            if blocks
            else ""
        )
        raw = await llm.llm_json(
            system=POSITIONED_SYSTEM,
            user=(
                f"Тип документа: {type_title(doc_type)}.\n"
                f"Ты представляешь сторону: {party_side.strip()}.\n\n"
                f"Оцени договор с её позиции:\n\n{llm.clip(document)}{blocks_hint}"
            ),
            # На длинном договоре ответ упирался в лимит и обрывался на
            # середине JSON — модуль падал целиком на ошибке парсинга.
            max_tokens=12_000,
        )
        return normalize_risk_result(raw, {item["anchor"] for item in clauses})


def normalize_risk_result(raw: dict, known_anchors: set[str]) -> dict:
    """Приводит ответ модели к контракту API и отбрасывает мусор."""
    items = raw.get("risks") if isinstance(raw, dict) else None
    risks: list[dict] = []

    for item in items or []:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip().lower()
        if category not in RISK_CATEGORIES:
            continue
        description = (item.get("description") or "").strip()
        if not description:
            continue
        level = str(item.get("level") or "").strip().lower()
        if level not in RISK_LEVELS:
            level = "medium"

        anchors = item.get("clause_anchors")
        if isinstance(anchors, str):
            anchors = [anchors]
        anchors = list(
            dict.fromkeys(
                str(anchor).strip()
                for anchor in (anchors or [])
                if str(anchor).strip() in known_anchors
            )
        )

        risks.append(
            {
                "category": category,
                "level": level,
                "description": description,
                "consequence": (item.get("consequence") or "").strip() or None,
                "mitigation": (item.get("mitigation") or "").strip() or None,
                "clause_anchors": anchors,
            }
        )

    score = raw.get("overall_score") if isinstance(raw, dict) else None
    try:
        score = max(0, min(100, int(score)))
    except (TypeError, ValueError):
        score = _score_from_levels(risks)

    overall_level = str((raw or {}).get("overall_level") or "").strip().lower()
    if overall_level not in RISK_LEVELS:
        overall_level = "high" if score >= 70 else "medium" if score >= 40 else "low"

    return {
        "risks": risks,
        "overall_score": score,
        "overall_level": overall_level,
        "summary": ((raw or {}).get("summary") or "").strip() or None,
    }


def _score_from_levels(risks: list[dict]) -> int:
    """Запасная оценка, если модель не вернула число."""
    if not risks:
        return 0
    weights = {"high": 30, "medium": 12, "low": 4}
    return min(100, sum(weights.get(risk["level"], 10) for risk in risks))
