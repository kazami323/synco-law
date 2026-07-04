"""Risk Agent — оценка юридических и финансовых рисков (Task 1.11)."""

import json

from app.utils import llm

SYSTEM = """Ты — эксперт по оценке договорных рисков в Узбекистане.
Оцениваешь юридические (исполнимость, вероятность споров), финансовые
(условия оплаты, штрафы, убытки) и операционные (расторжение, форс-мажор)
риски договора.

Формат ответа — JSON:
{
  "overall_score": 0-100,
  "category": "critical|high|medium|low",
  "risk_factors": [
    {"factor": "описание риска",
     "severity": 1-10,
     "impact": "financial|legal|operational"}
  ],
  "mitigation": ["мера снижения риска", ...],
  "recommendation": "итоговая рекомендация (согласовать / доработать / отклонить)"
}
Шкала: 0-39 low, 40-69 medium, 70-89 high, 90-100 critical."""


class RiskAgent:
    name = "risk_agent"

    async def assess_risk(
        self,
        contract_content: str,
        errors: list | None = None,
        legal_issues: list | None = None,
    ) -> dict:
        context = ""
        if errors:
            context += f"\n\nСтруктурные ошибки:\n{json.dumps(errors, ensure_ascii=False)[:4000]}"
        if legal_issues:
            context += f"\n\nЮридические проблемы:\n{json.dumps(legal_issues, ensure_ascii=False)[:4000]}"

        return await llm.llm_json(
            system=SYSTEM,
            user=f"Оцени риски договора:\n\n{llm.clip(contract_content)}{context}",
        )
