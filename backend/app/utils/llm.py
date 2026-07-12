"""Клиент Anthropic API и общие хелперы вызова LLM для агентов."""

import base64
import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from anthropic import AsyncAnthropic
from fastapi import HTTPException

from app.core.config import settings

_client: AsyncAnthropic | None = None


@dataclass
class UsageCollector:
    input_tokens: int = 0
    output_tokens: int = 0


_usage_collector: ContextVar[UsageCollector | None] = ContextVar(
    "ai_usage_collector", default=None
)


@contextmanager
def collect_usage():
    collector = UsageCollector()
    token = _usage_collector.set(collector)
    try:
        yield collector
    finally:
        _usage_collector.reset(token)


def get_anthropic_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY or None,
            timeout=settings.ANTHROPIC_TIMEOUT_SECONDS,
            max_retries=2,
        )
    return _client


def require_api_key() -> None:
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI недоступен: добавьте ANTHROPIC_API_KEY в backend/.env и перезапустите сервер",
        )


async def extract_pdf_text(pdf_data: bytes, filename: str) -> str:
    """Use Claude PDF vision as OCR fallback for image-only documents."""
    require_api_key()
    client = get_anthropic_client()
    try:
        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=16_000,
            system=(
                "Ты выполняешь точное OCR-распознавание юридических документов. "
                "Верни только полный распознанный текст без анализа и комментариев. "
                "Сохраняй заголовки, нумерацию, реквизиты и таблицы. "
                "Не додумывай неразборчивые фрагменты: отмечай их как [неразборчиво]."
            ),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": base64.b64encode(pdf_data).decode("ascii"),
                            },
                            "title": filename[:255],
                        },
                        {
                            "type": "text",
                            "text": "Распознай весь текст этого PDF-документа.",
                        },
                    ],
                }
            ],
            timeout=max(settings.ANTHROPIC_TIMEOUT_SECONDS, 180),
        )
    except Exception as exc:
        raise ValueError("Не удалось распознать сканированный PDF через AI OCR") from exc
    collector = _usage_collector.get()
    if collector is not None:
        collector.input_tokens += int(getattr(response.usage, "input_tokens", 0) or 0)
        collector.output_tokens += int(getattr(response.usage, "output_tokens", 0) or 0)
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        raise ValueError("Не удалось распознать текст сканированного PDF")
    return text


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
    collector = _usage_collector.get()
    if collector is not None:
        collector.input_tokens += int(getattr(response.usage, "input_tokens", 0) or 0)
        collector.output_tokens += int(getattr(response.usage, "output_tokens", 0) or 0)
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
