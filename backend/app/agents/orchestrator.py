"""Оркестратор анализа контрактов (Task 1.13).

Contract Analyzer и Law Agent работают параллельно, затем Risk Agent
получает их результаты. Итог агрегируется в отчёт с рекомендацией.
"""

import asyncio
import time

from app.agents.contract_analyzer import ContractAnalyzerAgent
from app.agents.draft_agent import DraftAgent
from app.agents.law_agent import LawAgent
from app.agents.risk_agent import RiskAgent


class ContractAnalysisOrchestrator:
    def __init__(self, lex_uz_key: str | None = None):
        self.analyzer = ContractAnalyzerAgent()
        self.law_agent = LawAgent(lex_uz_key)
        self.risk_agent = RiskAgent()
        self.draft_agent = DraftAgent()

    async def run_analysis(self, contract_id: str, contract_content: str) -> dict:
        timings: dict[str, int] = {}

        async def timed(name: str, coro):
            start = time.monotonic()
            result = await coro
            timings[name] = int((time.monotonic() - start) * 1000)
            return result

        analyzer_results, law_results = await asyncio.gather(
            timed("contract_analyzer", self.analyzer.analyze(contract_content)),
            timed("law_agent", self.law_agent.check_legislation(contract_content)),
        )
        risk_results = await timed(
            "risk_agent",
            self.risk_agent.assess_risk(
                contract_content,
                errors=analyzer_results.get("errors", []),
                legal_issues=law_results.get("legal_issues", []),
            ),
        )

        return {
            "contract_id": contract_id,
            "analysis": {
                "contract_analyzer": analyzer_results,
                "law_agent": law_results,
                "risk_agent": risk_results,
            },
            "timings_ms": timings,
            "overall_assessment": self._aggregate(
                analyzer_results, law_results, risk_results
            ),
            "next_steps": self._next_steps(law_results, risk_results),
        }

    @staticmethod
    def _aggregate(analyzer: dict, law: dict, risk: dict) -> dict:
        score = risk.get("overall_score", 100)
        return {
            "errors_found": len(analyzer.get("errors", [])),
            "legal_compliance": law.get("compliance_status", "unknown"),
            "risk_score": score,
            "risk_category": risk.get("category", "unknown"),
            "recommendation": "Можно согласовывать" if score < 40 else "Требуется доработка",
        }

    @staticmethod
    def _next_steps(law: dict, risk: dict) -> list[str]:
        steps: list[str] = []
        if law.get("compliance_status") == "non-compliant":
            steps.append("Устранить нарушения законодательства")
        if risk.get("overall_score", 100) >= 70:
            steps.append("Снизить риски по рекомендациям Risk Agent")
        if not steps:
            steps.append("Передать на согласование руководителю")
        return steps
