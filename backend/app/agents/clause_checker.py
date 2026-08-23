"""Модуль 1: сверка пунктов договора с правовой базой (ТЗ, раздел 4).

Работает пачками: для группы пунктов подбираются релевантные статьи из
локальной базы lex.uz, модель выносит вердикт по каждому пункту, а код
проверяет, что вердикт действительно опирается на переданную норму.

Главное правило: «противоречит» без подтверждённой статьи не выпускается
наружу. Юрист, сославшийся на несуществующую статью перед контрагентом, —
худший сценарий этого продукта, поэтому такой вердикт понижается до
«требует внимания» с honest-пометкой.
"""

from __future__ import annotations

from app.agents.response_standard import DEFAULT_LAWYER_NOTE
from app.core.document_types import law_hints, type_title
from app.db.models import ClauseVerdict
from app.utils import llm

# Сколько пунктов уходит в один запрос: больше — дешевле, но модель начинает
# «сливать» пункты друг с другом и терять точность привязки.
BATCH_SIZE = 6

VALID_VERDICTS = {v.value for v in ClauseVerdict}

SYSTEM = """Ты — юрист по договорному праву Республики Узбекистан.
Проверяешь ОТДЕЛЬНЫЕ ПУНКТЫ договора на соответствие законодательству РУз
(Гражданский кодекс, Трудовой кодекс, Налоговый кодекс, закон «О договорно-
правовой базе деятельности хозяйствующих субъектов»).

Тебе передают пронумерованные пункты договора и блок «Нормы из локальной базы
lex.uz» с идентификаторами [L1], [L2] и т. д.

ЖЁСТКИЕ ПРАВИЛА:
1. Опирайся ТОЛЬКО на переданные нормы. Не называй номера статей по памяти.
2. Если ни одна переданная норма пункт не регулирует — вердикт "no_norm".
   Это нормальный и честный ответ, а не поражение.
3. Вердикт "conflicts" допустим, только если ты указал конкретный source_id
   из переданного блока норм. Без источника используй "attention".
4. Для "conflicts" обязательно дай suggested_text — готовую формулировку
   пункта на замену, которую юрист может вставить в договор без переписывания.
5. Заголовки разделов («2. ЦЕНА И ПОРЯДОК РАСЧЁТОВ») содержания не несут —
   для них вердикт "no_norm" с коротким rationale.
6. rationale — 1-2 предложения по-русски, юридическим языком, по существу.

Вердикты (строго один из четырёх):
  compliant  — пункт соответствует норме
  conflicts  — пункт противоречит конкретной норме
  attention  — формально не противоречит, но создаёт правовой риск
  no_norm    — среди переданных норм регулирующей нет

Формат ответа — JSON:
{
  "verdicts": [
    {"anchor": "1.1",
     "verdict": "compliant|conflicts|attention|no_norm",
     "rationale": "почему именно такой вердикт",
     "source_ids": ["L1"],
     "suggested_text": "формулировка на замену или null"}
  ]
}
Один объект на каждый переданный пункт, anchor копируй дословно."""


class ClauseCheckerAgent:
    name = "clause_checker"

    async def check_batch(
        self,
        clauses: list[dict],
        sources: list[dict],
        *,
        doc_type: str | None = None,
        laws_block: str = "",
    ) -> list[dict]:
        """clauses: [{anchor, number, title, content}] -> список вердиктов."""
        if not clauses:
            return []

        clauses_block = "\n\n".join(
            f"[{item['anchor']}] {item.get('title') or ''}\n{llm.clip(item['content'], 3000)}".strip()
            for item in clauses
        )
        type_block = (
            f"Тип документа: {type_title(doc_type)}.\n" if doc_type else ""
        )
        norms_block = (
            f"\n\nНормы из локальной базы lex.uz:\n{laws_block}"
            if laws_block
            else "\n\nНормы из локальной базы lex.uz: не найдены."
        )

        raw = await llm.llm_json(
            system=SYSTEM,
            user=(
                f"{type_block}Проверь каждый пункт договора:\n\n"
                f"{clauses_block}{norms_block}"
            ),
            max_tokens=6000,
        )
        return normalize_verdicts(raw, clauses, sources)


def normalize_verdicts(
    raw: dict, clauses: list[dict], sources: list[dict]
) -> list[dict]:
    """Приводит ответ модели к контракту, который ждёт остальная система.

    Здесь же работает защита от выдуманных норм: ссылка засчитывается, только
    если её идентификатор указывает на реально переданный источник.
    """
    by_anchor: dict[str, dict] = {}
    items = raw.get("verdicts") if isinstance(raw, dict) else None
    for item in items or []:
        if isinstance(item, dict) and item.get("anchor"):
            by_anchor[str(item["anchor"]).strip()] = item

    results: list[dict] = []
    for clause in clauses:
        anchor = clause["anchor"]
        item = by_anchor.get(anchor) or {}
        verdict = str(item.get("verdict") or "").strip().lower()
        if verdict not in VALID_VERDICTS:
            verdict = ClauseVerdict.NO_NORM.value

        resolved = _resolve_sources(item.get("source_ids"), sources)
        rationale = (item.get("rationale") or "").strip() or None
        suggested = (item.get("suggested_text") or "").strip() or None

        # Обвинение в противоречии без подтверждённой нормы не выпускаем.
        if verdict == ClauseVerdict.CONFLICTS.value and not resolved:
            verdict = ClauseVerdict.ATTENTION.value
            rationale = _prefix(
                rationale,
                "Норма-основание не подтверждена локальной базой lex.uz, "
                "требуется проверка первоисточника.",
            )
        if verdict == ClauseVerdict.NO_NORM.value:
            resolved = []
            suggested = None

        results.append(
            {
                "anchor": anchor,
                "verdict": verdict,
                "rationale": rationale,
                "suggested_text": suggested,
                "sources": resolved,
                "lawyer_note": DEFAULT_LAWYER_NOTE,
            }
        )
    return results


def build_query(clauses: list[dict], doc_type: str | None) -> str:
    """Поисковый запрос к правовой базе по пачке пунктов."""
    body = " ".join(
        f"{item.get('title') or ''} {item.get('content') or ''}"[:900]
        for item in clauses
    )
    hints = " ".join(law_hints(doc_type))
    return f"{body}\n{hints}".strip()


def source_snapshot(source: dict) -> dict:
    """Снапшот нормы на дату проверки — для воспроизводимости результата."""
    return {
        "document_title": source.get("document_title"),
        "document_number": source.get("document_number"),
        "article_number": source.get("article_number"),
        "article_title": source.get("article_title"),
        "content": (source.get("content") or "")[:2000],
        "url": source.get("url"),
        "current_revision_date": source.get("current_revision_date"),
        "status": source.get("status"),
    }


def _resolve_sources(source_ids, sources: list[dict]) -> list[dict]:
    if not source_ids or not sources:
        return []
    if isinstance(source_ids, str):
        source_ids = [source_ids]
    resolved: list[dict] = []
    seen: set[int] = set()
    for ref in source_ids:
        index = _source_index(ref)
        if index is None or not (0 <= index < len(sources)) or index in seen:
            continue
        seen.add(index)
        resolved.append(source_snapshot(sources[index]))
    return resolved


def _source_index(ref) -> int | None:
    text = str(ref or "").strip().upper()
    if text.startswith("L"):
        text = text[1:]
    return int(text) - 1 if text.isdigit() else None


def _prefix(rationale: str | None, note: str) -> str:
    return f"{note} {rationale}".strip() if rationale else note
