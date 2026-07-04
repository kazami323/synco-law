"""Law Agent — проверка на соответствие законодательству Узбекистана (Task 1.10).

Если задан LEX_UZ_API_KEY, подтягивает нормы с lex.uz; иначе опирается на
знания модели о ГК, ТК и НК РУз (с пометкой в результате).
"""

import json

import httpx

from app.core.config import settings
from app.utils import llm

SYSTEM = """Ты — эксперт по законодательству Республики Узбекистан
(Гражданский кодекс, Трудовой кодекс, Налоговый кодекс, закон «О договорно-
правовой базе деятельности хозяйствующих субъектов»).
Проверяешь договор на соответствие законодательству РУз.

Формат ответа — JSON:
{
  "legal_issues": [
    {"issue": "описание проблемы",
     "applicable_law": "название НПА",
     "article": "статья",
     "violation_type": "conflict|missing|unclear",
     "recommendation": "как привести в соответствие"}
  ],
  "compliance_status": "compliant|partial|non-compliant",
  "recommendations": ["общая рекомендация", ...]
}"""


class LawAgent:
    name = "law_agent"

    def __init__(self, lex_uz_api_key: str | None = None):
        self.lex_uz_api_key = lex_uz_api_key or settings.LEX_UZ_API_KEY

    async def check_legislation(
        self, contract_content: str, errors: list | None = None
    ) -> dict:
        laws = await self._fetch_relevant_laws(contract_content)
        laws_block = (
            f"\n\nНормы из lex.uz:\n{json.dumps(laws, ensure_ascii=False)[:8000]}"
            if laws
            else ""
        )
        errors_block = (
            f"\n\nУже найденные структурные ошибки:\n{json.dumps(errors, ensure_ascii=False)[:4000]}"
            if errors
            else ""
        )
        result = await llm.llm_json(
            system=SYSTEM,
            user=(
                f"Проверь договор на соответствие законодательству РУз:"
                f"\n\n{llm.clip(contract_content)}{errors_block}{laws_block}"
            ),
        )
        result["source"] = "lex.uz" if laws else "model_knowledge"
        return result

    async def _fetch_relevant_laws(self, content: str) -> list:
        """Релевантные НПА с lex.uz; без ключа или при ошибке — пустой список."""
        if not self.lex_uz_api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://api.lex.uz/search",
                    params={"q": content[:500]},
                    headers={"Authorization": f"Bearer {self.lex_uz_api_key}"},
                )
                response.raise_for_status()
                return response.json()
        except Exception:
            return []
