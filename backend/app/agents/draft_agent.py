"""Draft Agent — генерация документов (ТЗ, раздел 3.1).

Два шага ТЗ:

* extract_parameters — из свободной речи или текста вытягивает стороны, суммы,
  сроки и санкции. Результат показывается юристу карточкой и генерацией НЕ
  является: пока юрист не подтвердил параметры, договор не составляется.
* create_contract — собирает документ из шаблона (если выбран), подтверждённых
  параметров и обязательных блоков, предусмотренных типом документа.
"""

import json

from app.core.document_types import required_blocks, type_title
from app.utils import llm

SYSTEM = """Ты — юрист, составляющий договоры по законодательству
Республики Узбекистан. Пишешь полный, готовый к использованию текст договора
на русском языке.

Требования к тексту:
- нумерация вида «1.», «1.1.», «1.1.1.» — по ней документ разбирается на пункты;
- каждый раздел начинается со строки-заголовка с номером;
- один пункт — одно условие; не сваливай несколько обязательств в абзац;
- никаких пояснений и комментариев от себя, только текст договора;
- никаких плейсхолдеров вида [указать], если данные переданы; если данных нет,
  оставляй прочерк «__________», чтобы юрист сразу видел, что заполнить."""

EXTRACT_SYSTEM = """Ты — помощник юриста. Из свободного описания (надиктованного
или набранного) вытаскиваешь параметры будущего договора.

ЖЁСТКИЕ ПРАВИЛА:
1. Извлекай только то, что реально сказано. Ничего не додумывай: пустое поле
   лучше выдуманного — юрист будет проверять эту карточку глазами.
2. Суммы, проценты и сроки переноси дословно, как названы («30%», «60 дней»,
   «0,1% в день»).
3. Стороны — с их ролью в договоре и организационно-правовой формой, если она
   названа («ООО», «ИП»).

Формат ответа — JSON:
{
  "contract_type": "supply|service|contracting|lease|purchase|employment|nda|license|amendment|other или null",
  "parties": [{"role": "Поставщик", "name": "ООО «Альфа»", "form": "ООО"}],
  "subject": "предмет договора",
  "amount": "сумма как названа или null",
  "currency": "UZS|USD|EUR или null",
  "payment_terms": "порядок расчётов: предоплата, отсрочка",
  "deadlines": [{"what": "поставка", "value": "30 дней"}],
  "penalties": [{"what": "просрочка поставки", "value": "0,1% в день"}],
  "jurisdiction": "подсудность или null",
  "other_terms": ["прочие названные условия"]
}"""


class DraftAgent:
    name = "draft_agent"

    async def extract_parameters(self, text: str) -> dict:
        """Карточка параметров для подтверждения юристом (ТЗ, шаг 3)."""
        raw = await llm.llm_json(
            system=EXTRACT_SYSTEM,
            user=f"Извлеки параметры договора из описания:\n\n{llm.clip(text, 12_000)}",
            max_tokens=2500,
        )
        return _normalize_parameters(raw)

    async def create_contract(
        self,
        contract_type: str,
        requirements: dict,
        *,
        template: str | None = None,
        project_context: dict | None = None,
    ) -> str:
        blocks = required_blocks(contract_type)
        blocks_block = (
            "\n\nОбязательные блоки для этого типа документа:\n- "
            + "\n- ".join(blocks)
            if blocks
            else ""
        )
        template_block = (
            "\n\nБери за основу шаблон организации, сохраняя его структуру и "
            f"формулировки, и подставляй в него данные:\n\n{llm.clip(template, 20_000)}"
            if template
            else "\n\nШаблон не выбран: используй общую структуру, принятую для "
            "этого типа документа."
        )
        context_block = (
            "\n\nОбщий контекст проекта (стороны, суммы, сроки):\n"
            f"{json.dumps(project_context, ensure_ascii=False, indent=2)}"
            if project_context
            else ""
        )

        return await llm.llm_text(
            system=SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Составь документ: {type_title(contract_type)}.\n\n"
                        "Подтверждённые юристом параметры:\n"
                        f"{json.dumps(requirements, ensure_ascii=False, indent=2)}"
                        f"{context_block}{blocks_block}{template_block}"
                    ),
                }
            ],
            max_tokens=8000,
        )

    async def edit_section(
        self, contract_content: str, section: str, instruction: str
    ) -> str:
        return await llm.llm_text(
            system=SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Вот договор:\n\n{llm.clip(contract_content)}\n\n"
                        f"Отредактируй раздел «{section}»: {instruction}\n"
                        f"Верни полный обновлённый текст договора."
                    ),
                }
            ],
            max_tokens=8000,
        )


def _normalize_parameters(raw: dict) -> dict:
    """Приводит карточку к предсказуемой форме — её рисует интерфейс."""
    if not isinstance(raw, dict):
        raw = {}

    def _text(value):
        value = (str(value).strip() if value is not None else "")
        return value or None

    def _dicts(value, keys):
        items = []
        for item in value or []:
            if isinstance(item, dict):
                cleaned = {key: _text(item.get(key)) for key in keys}
                if any(cleaned.values()):
                    items.append(cleaned)
            elif isinstance(item, str) and item.strip():
                cleaned = dict.fromkeys(keys)
                cleaned[keys[0]] = item.strip()
                items.append(cleaned)
        return items

    return {
        "contract_type": _text(raw.get("contract_type")),
        "parties": _dicts(raw.get("parties"), ["role", "name", "form"]),
        "subject": _text(raw.get("subject")),
        "amount": _text(raw.get("amount")),
        "currency": _text(raw.get("currency")),
        "payment_terms": _text(raw.get("payment_terms")),
        "deadlines": _dicts(raw.get("deadlines"), ["what", "value"]),
        "penalties": _dicts(raw.get("penalties"), ["what", "value"]),
        "jurisdiction": _text(raw.get("jurisdiction")),
        "other_terms": [
            term.strip()
            for term in (raw.get("other_terms") or [])
            if isinstance(term, str) and term.strip()
        ],
    }
