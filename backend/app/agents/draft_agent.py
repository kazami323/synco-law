"""Draft Agent — генерация контрактов по требованиям и редактирование разделов.

Реализация — Weeks 7-8 (Task 1.12).
"""

from anthropic import AsyncAnthropic

from app.core.config import settings


class DraftAgent:
    name = "draft_agent"

    def __init__(self, llm: AsyncAnthropic, model: str | None = None):
        self.llm = llm
        self.model = model or settings.ANTHROPIC_MODEL

    async def create_contract(self, contract_type: str, requirements: dict) -> str:
        raise NotImplementedError("Implemented in Weeks 7-8")

    async def edit_section(
        self, contract_content: str, section_number: str, new_text: str
    ) -> str:
        raise NotImplementedError("Implemented in Weeks 7-8")
