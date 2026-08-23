"""Модуль 2: смысловые расхождения внутри документа (ТЗ, раздел 4).

Разбор перекрёстных ссылок, обозначений сторон и терминов делает код
(services/logic_check.py). Здесь остаётся то, что требует понимания смысла:
противоречия по срокам и суммам, дублирование условий и разрывы в цепочках
процедур.

Каждая находка обязана указывать минимум два конфликтующих пункта — ТЗ
требует показывать их рядом, чтобы юрист видел суть за секунду. Находка с
одним пунктом отбрасывается как непригодная.
"""

from __future__ import annotations

from app.services.logic_check import AI_CATEGORIES, LOGIC_CATEGORIES
from app.utils import llm

SYSTEM = """Ты — юрист, вычитывающий договор на внутреннюю непротиворечивость.
Ты НЕ проверяешь соответствие законодательству — только согласованность
документа с самим собой.

Тебе передают договор, разбитый на пронумерованные пункты вида [1.1], [4.2].

Ищешь только эти категории:
  deadlines    — противоречия по срокам: в одном пункте оплата 30 дней,
                 в другом 45; срок поставки не согласуется со сроком приёмки
  amounts      — противоречия по суммам: цифры в тексте, в приложении и в
                 реквизитах расходятся; процент предоплаты не сходится с суммой
  duplication  — одно и то же условие описано дважды по-разному
  chain_gaps   — разрывы в цепочках: прописан порядок расторжения, но нет
                 порядка уведомления; предусмотрен штраф, но не сказано, как
                 он начисляется и в какой срок уплачивается

ЖЁСТКИЕ ПРАВИЛА:
1. Каждая находка обязана указывать МИНИМУМ ДВА конфликтующих пункта в
   clause_anchors. Если второй пункт назвать невозможно — не сообщай находку.
2. Anchors копируй дословно из переданного текста, без выдумывания номеров.
3. Не сообщай о «потенциальных» и «возможных» расхождениях. Только то, что
   видно в тексте: два конкретных условия, которые не могут действовать
   одновременно.
4. description — по-русски, с указанием конкретных значений: «п. 2.3 — оплата
   в течение 30 дней, п. 4.1 — пеня начисляется с 15-го дня».
5. suggestion — конкретная правка, а не «привести в соответствие».

Формат ответа — JSON:
{
  "findings": [
    {"category": "deadlines|amounts|duplication|chain_gaps",
     "description": "что именно расходится, с числами",
     "suggestion": "как исправить",
     "clause_anchors": ["2.3", "4.1"]}
  ]
}
Если расхождений нет — верни {"findings": []}. Пустой ответ лучше выдуманного."""


class LogicAgent:
    name = "logic_agent"

    async def find_conflicts(self, clauses: list[dict]) -> list[dict]:
        """clauses: [{anchor, title, content}] -> список находок."""
        if len(clauses) < 2:
            return []

        document = "\n\n".join(
            f"[{item['anchor']}] {item.get('title') or ''}\n{item['content']}".strip()
            for item in clauses
        )
        raw = await llm.llm_json(
            system=SYSTEM,
            user=f"Найди расхождения внутри договора:\n\n{llm.clip(document)}",
            max_tokens=6000,
        )
        known_anchors = {item["anchor"] for item in clauses}
        return normalize_findings(raw, known_anchors)


def normalize_findings(raw: dict, known_anchors: set[str]) -> list[dict]:
    """Отбрасывает находки, которые нельзя показать юристу парой пунктов."""
    items = raw.get("findings") if isinstance(raw, dict) else None
    results: list[dict] = []

    for item in items or []:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip().lower()
        if category not in AI_CATEGORIES or category not in LOGIC_CATEGORIES:
            continue
        description = (item.get("description") or "").strip()
        if not description:
            continue

        anchors = item.get("clause_anchors")
        if isinstance(anchors, str):
            anchors = [anchors]
        anchors = [
            str(anchor).strip()
            for anchor in (anchors or [])
            if str(anchor).strip() in known_anchors
        ]
        anchors = list(dict.fromkeys(anchors))
        # Обещание ТЗ — показать оба конфликтующих пункта рядом. Одна ссылка
        # это обещание не выполняет, такую находку не показываем вовсе.
        if len(anchors) < 2:
            continue

        results.append(
            {
                "category": category,
                "description": description,
                "suggestion": (item.get("suggestion") or "").strip() or None,
                "clause_anchors": anchors,
                "detected_by": "ai",
            }
        )
    return results
