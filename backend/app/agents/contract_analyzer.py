"""Contract Analyzer — структурный анализ контракта (Task 1.9).

Ищет ошибки и противоречия между разделами, отсутствующие существенные
условия, неоднозначные формулировки.
"""

from app.utils import llm

SYSTEM = """Ты — опытный юрист-аналитик коммерческих договоров в Узбекистане.
Анализируешь структуру договора: ошибки, противоречия между разделами,
отсутствующие существенные условия (стороны, предмет, цена, сроки,
ответственность), неоднозначные формулировки.

Формат ответа — JSON:
{
  "errors": [
    {"severity": "critical|warning|info",
     "location": "раздел/пункт",
     "description": "что не так",
     "recommendation": "как исправить"}
  ],
  "missing_terms": ["отсутствующее условие", ...],
  "summary": "краткая общая оценка структуры договора (2-3 предложения)"
}"""


class ContractAnalyzerAgent:
    name = "contract_analyzer"

    async def analyze(self, contract_content: str) -> dict:
        return await llm.llm_json(
            system=SYSTEM,
            user=f"Проанализируй договор:\n\n{llm.clip(contract_content)}",
        )
