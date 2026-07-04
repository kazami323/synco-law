"""Draft Agent — генерация контрактов по требованиям (Task 1.12)."""

import json

from app.utils import llm

SYSTEM = """Ты — юрист, составляющий договоры по законодательству
Республики Узбекистан. Пишешь полный, готовый к использованию текст договора
на русском языке со стандартными разделами: стороны, предмет, цена и порядок
расчётов, права и обязанности, ответственность и неустойки, форс-мажор,
разрешение споров, срок действия и расторжение, реквизиты.
Используй нумерацию разделов и пунктов. Не добавляй комментарии — только текст договора."""

TYPE_LABELS = {
    "purchase": "договор купли-продажи / поставки",
    "lease": "договор аренды",
    "service": "договор подряда / возмездного оказания услуг",
    "nda": "соглашение о неразглашении (NDA)",
    "employment": "трудовой договор",
    "other": "договор",
}


class DraftAgent:
    name = "draft_agent"

    async def create_contract(self, contract_type: str, requirements: dict) -> str:
        type_label = TYPE_LABELS.get(contract_type, "договор")
        return await llm.llm_text(
            system=SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Составь {type_label}.\n\nТребования и данные:\n"
                        f"{json.dumps(requirements, ensure_ascii=False, indent=2)}"
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
