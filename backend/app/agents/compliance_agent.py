"""Compliance Agent — проверка контрактов на соответствие внутренним
политикам организации (Phase 2)."""

from app.utils import llm

SYSTEM = """Ты — комплаенс-офицер компании в Узбекистане. Проверяешь договор
на соответствие внутренним политикам организации, которые тебе передали.
Оценивай только по этим политикам — соответствие законодательству проверяет
другой агент.

Формат ответа — JSON:
{
  "violations": [
    {"policy": "какая политика нарушена",
     "description": "в чём нарушение",
     "severity": "critical|warning|info",
     "recommendation": "как устранить"}
  ],
  "compliance_score": 0-100,
  "status": "compliant|partial|non-compliant",
  "summary": "краткий вывод (1-2 предложения)"
}
compliance_score: 100 — нарушений нет, 0 — грубые нарушения ключевых политик."""


class ComplianceAgent:
    name = "compliance_agent"

    async def check(self, contract_content: str, policies: str) -> dict:
        return await llm.llm_json(
            system=SYSTEM,
            user=(
                f"Внутренние политики организации:\n---\n{llm.clip(policies, 20_000)}\n---\n\n"
                f"Проверь договор на их соблюдение:\n\n{llm.clip(contract_content)}"
            ),
        )
