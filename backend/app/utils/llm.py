"""Клиент Anthropic API и общие хелперы вызова LLM для агентов."""

import json
import re

from anthropic import AsyncAnthropic
from fastapi import HTTPException

from app.core.config import settings

_client: AsyncAnthropic | None = None


def get_anthropic_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY or None)
    return _client


def require_api_key() -> None:
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI недоступен: добавьте ANTHROPIC_API_KEY в backend/.env и перезапустите сервер",
        )


async def llm_text(
    *,
    system: str,
    messages: list[dict],
    max_tokens: int = 4000,
) -> str:
    """Обычный текстовый ответ модели."""
    client = get_anthropic_client()
    response = await client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return "".join(
        block.text for block in response.content if block.type == "text"
    )


def extract_json(text: str) -> dict:
    """Достаёт JSON-объект из ответа модели (в т.ч. из ```json-блока)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"Модель не вернула JSON: {text[:200]}")
    return json.loads(text[start : end + 1])


async def llm_json(
    *,
    system: str,
    user: str,
    max_tokens: int = 4000,
) -> dict:
    """Запрос с JSON-ответом; парсит и возвращает dict."""
    text = await llm_text(
        system=system + "\n\nОтвечай ТОЛЬКО валидным JSON без пояснений.",
        messages=[{"role": "user", "content": user}],
        max_tokens=max_tokens,
    )
    return extract_json(text)


# Контракты бывают длинными: ограничиваем контекст, чтобы не выйти за бюджет
MAX_CONTRACT_CHARS = 60_000


def clip(text: str, limit: int = MAX_CONTRACT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[...текст обрезан для анализа...]"
