"""Оркестратор анализа контрактов (LangGraph) — Weeks 7-8 (Task 1.13).

Параллельно запускает Contract Analyzer, Law Agent и Risk Agent,
агрегирует результаты в итоговый отчёт.
"""

from anthropic import AsyncAnthropic

from app.agents.contract_analyzer import ContractAnalyzerAgent
from app.agents.draft_agent import DraftAgent
from app.agents.law_agent import LawAgent
from app.agents.risk_agent import RiskAgent


class ContractAnalysisOrchestrator:
    def __init__(self, llm: AsyncAnthropic, lex_uz_key: str | None = None):
        self.analyzer = ContractAnalyzerAgent(llm)
        self.law_agent = LawAgent(llm, lex_uz_key)
        self.risk_agent = RiskAgent(llm)
        self.draft_agent = DraftAgent(llm)

    async def run_analysis(self, contract_id: str, contract_content: str) -> dict:
        """Полный цикл анализа: структура -> закон -> риски -> итоговый отчёт."""
        raise NotImplementedError("Implemented in Weeks 7-8")
