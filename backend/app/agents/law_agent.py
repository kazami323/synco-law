"""Law Agent — проверка контракта на соответствие законодательству Узбекистана.

Использует lex.uz API (ГК, ТК, НК). Реализация — Weeks 7-8 (Task 1.10).
"""

from anthropic import AsyncAnthropic

from app.core.config import settings


class LawAgent:
    name = "law_agent"

    def __init__(self, llm: AsyncAnthropic, lex_uz_api_key: str | None = None, model: str | None = None):
        self.llm = llm
        self.lex_uz_api_key = lex_uz_api_key or settings.LEX_UZ_API_KEY
        self.model = model or settings.ANTHROPIC_MODEL

    async def check_legislation(self, contract_content: str, errors: list) -> dict:
        """Возвращает {"legal_issues": [...], "compliance_status": "...", "recommendations": [...]}."""
        raise NotImplementedError("Implemented in Weeks 7-8")

    async def _fetch_relevant_laws(self, content: str) -> list:
        raise NotImplementedError("Implemented in Weeks 7-8")
