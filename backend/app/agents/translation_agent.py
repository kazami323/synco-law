"""Translation Agent — юридический перевод контрактов ru/uz/en (Phase 2)."""

from app.utils import llm

SYSTEM = """Ты — профессиональный юридический переводчик, работающий с
договорами по законодательству Республики Узбекистан.
Переводишь точно, сохраняя юридическую терминологию, нумерацию разделов
и структуру документа. Термины без общепринятого эквивалента поясняй в
скобках. Не добавляй комментарии — возвращай только перевод."""

LANG_LABELS = {
    "ru": "русский",
    "uz": "узбекский (латиница)",
    "uz_cyrl": "узбекский (кириллица)",
    "en": "английский",
}


class TranslationAgent:
    name = "translation_agent"

    async def translate(self, content: str, target_lang: str) -> str:
        label = LANG_LABELS.get(target_lang)
        if label is None:
            raise ValueError(f"Unsupported language: {target_lang}")
        return await llm.llm_text(
            system=SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Переведи документ на {label} язык:\n\n"
                        f"{llm.clip(content)}"
                    ),
                }
            ],
            max_tokens=8000,
        )
