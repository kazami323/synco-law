"""Contract Analyzer Agent — структурный анализ контракта.

Ищет ошибки и противоречия между разделами, отсутствующие существенные
условия, неоднозначные формулировки. Реализация — Weeks 7-8 (Task 1.9).
"""

from anthropic import AsyncAnthropic

from app.core.config import settings


class ContractAnalyzerAgent:
    name = "contract_analyzer"

    def __init__(self, llm: AsyncAnthropic, model: str | None = None):
        self.llm = llm
        self.model = model or settings.ANTHROPIC_MODEL

    async def analyze(self, contract_content: str) -> dict:
        """Возвращает {"errors": [...], "missing_terms": [...], "summary": "..."}."""
        raise NotImplementedError("Implemented in Weeks 7-8")
