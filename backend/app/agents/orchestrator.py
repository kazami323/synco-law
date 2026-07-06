"""Оркестратор анализа контрактов (Task 1.13).

Contract Analyzer и Law Agent работают параллельно, затем Risk Agent
получает их результаты. Итог агрегируется в отчёт с рекомендацией.
"""

import asyncio
import time

from app.agents.compliance_agent import ComplianceAgent
from app.agents.contract_analyzer import ContractAnalyzerAgent
from app.agents.draft_agent import DraftAgent
from app.agents.law_agent import LawAgent
from app.agents.risk_agent import RiskAgent
from app.agents.translation_agent import TranslationAgent


class ContractAnalysisOrchestrator:
    def __init__(self, lex_uz_key: str | None = None):
        self.analyzer = ContractAnalyzerAgent()
        self.law_agent = LawAgent(lex_uz_key)
        self.risk_agent = RiskAgent()
        self.draft_agent = DraftAgent()
        self.compliance_agent = ComplianceAgent()
        self.translation_agent = TranslationAgent()

    async def run_analysis(
        self,
        contract_id: str,
        contract_content: str,
        compliance_policies: str | None = None,
    ) -> dict:
        timings: dict[str, int] = {}

        async def timed(name: str, coro):
            start = time.monotonic()
            result = await coro
            timings[name] = int((time.monotonic() - start) * 1000)
            return result

        # Параллельная волна: структура + закон (+ комплаенс, если политики заданы)
        wave = [
            timed("contract_analyzer", self.analyzer.analyze(contract_content)),
            timed("law_agent", self.law_agent.check_legislation(contract_content)),
        ]
        if compliance_policies and compliance_policies.strip():
            wave.append(
                timed(
                    "compliance_agent",
                    self.compliance_agent.check(contract_content, compliance_policies),
                )
            )
        results = await asyncio.gather(*wave)
        analyzer_results, law_results = results[0], results[1]
        compliance_results = results[2] if len(results) > 2 else None

        risk_results = await timed(
            "risk_agent",
            self.risk_agent.assess_risk(
                contract_content,
                errors=analyzer_results.get("errors", []),
                legal_issues=law_results.get("legal_issues", []),
            ),
        )

        analysis = {
            "contract_analyzer": analyzer_results,
            "law_agent": law_results,
            "risk_agent": risk_results,
        }
        if compliance_results is not None:
            analysis["compliance_agent"] = compliance_results

        return {
            "contract_id": contract_id,
            "analysis": analysis,
            "timings_ms": timings,
            "overall_assessment": self._aggregate(
                analyzer_results, law_results, risk_results, compliance_results
            ),
            "next_steps": self._next_steps(
                law_results, risk_results, compliance_results
            ),
        }

    @staticmethod
    def _aggregate(
        analyzer: dict, law: dict, risk: dict, compliance: dict | None = None
    ) -> dict:
        score = risk.get("overall_score", 100)
        needs_work = score >= 40 or (
            compliance is not None and compliance.get("status") == "non-compliant"
        )
        result = {
            "errors_found": len(analyzer.get("errors", [])),
            "legal_compliance": law.get("compliance_status", "unknown"),
            "risk_score": score,
            "risk_category": risk.get("category", "unknown"),
            "recommendation": "Требуется доработка" if needs_work else "Можно согласовывать",
        }
        if compliance is not None:
            result["policy_compliance"] = compliance.get("status", "unknown")
        return result

    @staticmethod
    def _next_steps(
        law: dict, risk: dict, compliance: dict | None = None
    ) -> list[str]:
        steps: list[str] = []
        if law.get("compliance_status") == "non-compliant":
            steps.append("Устранить нарушения законодательства")
        if compliance is not None and compliance.get("status") != "compliant":
            steps.append("Привести договор в соответствие внутренним политикам")
        if risk.get("overall_score", 100) >= 70:
            steps.append("Снизить риски по рекомендациям Risk Agent")
        if not steps:
            steps.append("Передать на согласование руководителю")
        return steps
