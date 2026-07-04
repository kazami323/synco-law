"""Risk Agent — оценка юридических и финансовых рисков контракта.

Возвращает risk score 0-100, категорию и рекомендации по митигации.
Реализация — Weeks 7-8 (Task 1.11).
"""

from anthropic import AsyncAnthropic

from app.core.config import settings


class RiskAgent:
    name = "risk_agent"

    def __init__(self, llm: AsyncAnthropic, model: str | None = None):
        self.llm = llm
        self.model = model or settings.ANTHROPIC_MODEL

    async def assess_risk(
        self, contract_content: str, errors: list, legal_issues: list
    ) -> dict:
        """Возвращает {"overall_score": 0-100, "category": "...", "risk_factors": [...], ...}."""
        raise NotImplementedError("Implemented in Weeks 7-8")
