"""Клиент Anthropic API и общие хелперы вызова LLM для агентов."""

import asyncio
import base64
import io
import json
import logging
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from anthropic import AsyncAnthropic
from fastapi import HTTPException
from pypdf import PdfReader, PdfWriter

from app.core.config import settings

logger = logging.getLogger("app.llm")

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


# OCR сканов: у Claude API лимиты на PDF (100 страниц, ~32 МБ запроса),
# а один вызов на весь скан ещё и упирается в таймаут. Поэтому режем PDF
# на куски и распознаём их параллельно.
OCR_CHUNK_PAGES = 10
OCR_MAX_PAGES = 150
OCR_MAX_CHUNK_BYTES = 25 * 1024 * 1024  # base64 раздувает на треть, лимит API 32 МБ
OCR_PARALLEL = 5

OCR_SYSTEM = (
    "Ты выполняешь точное OCR-распознавание юридических документов. "
    "Верни только полный распознанный текст без анализа и комментариев. "
    "Сохраняй заголовки, нумерацию, реквизиты и таблицы. "
    "Не додумывай неразборчивые фрагменты: отмечай их как [неразборчиво]."
)


def _pdf_slice(reader: PdfReader, start: int, stop: int) -> bytes:
    writer = PdfWriter()
    for index in range(start, stop):
        writer.add_page(reader.pages[index])
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _pdf_chunks(pdf_data: bytes) -> list[tuple[str, bytes]]:
    """Нарезка PDF на куски для OCR: [(подпись 'стр. 1-10', байты), ...]."""
    reader = PdfReader(io.BytesIO(pdf_data))
    total = len(reader.pages)
    if total > OCR_MAX_PAGES:
        raise ValueError(
            f"Скан из {total} страниц слишком большой для распознавания. "
            f"Разбейте файл на части до {OCR_MAX_PAGES} страниц."
        )
    chunks: list[tuple[str, bytes]] = []
    for start in range(0, total, OCR_CHUNK_PAGES):
        stop = min(start + OCR_CHUNK_PAGES, total)
        data = _pdf_slice(reader, start, stop)
        if len(data) <= OCR_MAX_CHUNK_BYTES:
            chunks.append((f"стр. {start + 1}-{stop}", data))
            continue
        # Кусок слишком тяжёлый (жирные сканы) — постранично
        for page in range(start, stop):
            page_data = _pdf_slice(reader, page, page + 1)
            if len(page_data) > OCR_MAX_CHUNK_BYTES:
                raise ValueError(
                    f"Страница {page + 1} скана весит больше 25 МБ — "
                    "пересканируйте документ с меньшим разрешением."
                )
            chunks.append((f"стр. {page + 1}", page_data))
    return chunks


async def _ocr_chunk(label: str, data: bytes, filename: str) -> str:
    client = get_anthropic_client()
    try:
        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=16_000,
            system=OCR_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": base64.b64encode(data).decode("ascii"),
                            },
                            "title": f"{filename[:200]} ({label})",
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
        # Настоящая причина — в лог; пользователю — компактная суть
        logger.exception("OCR failed for %s %s", filename, label)
        reason = str(exc).strip().splitlines()[0][:180] if str(exc) else "нет ответа API"
        raise ValueError(f"Ошибка распознавания ({label}): {reason}") from exc
    collector = _usage_collector.get()
    if collector is not None:
        collector.input_tokens += int(getattr(response.usage, "input_tokens", 0) or 0)
        collector.output_tokens += int(getattr(response.usage, "output_tokens", 0) or 0)
    return "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()


async def extract_pdf_text(pdf_data: bytes, filename: str) -> str:
    """OCR скана через Claude PDF vision: кусками, параллельно."""
    require_api_key()
    try:
        chunks = _pdf_chunks(pdf_data)
    except ValueError:
        raise
    except Exception as exc:
        logger.exception("OCR: cannot split PDF %s", filename)
        raise ValueError("Не удалось прочитать структуру PDF для распознавания") from exc

    semaphore = asyncio.Semaphore(OCR_PARALLEL)

    async def bounded(label: str, data: bytes) -> str:
        async with semaphore:
            return await _ocr_chunk(label, data, filename)

    parts = await asyncio.gather(*(bounded(label, data) for label, data in chunks))
    text = "\n\n".join(part for part in parts if part).strip()
    if not text:
        raise ValueError("Не удалось распознать текст сканированного PDF")
    return text


async def llm_text_stream(
    *,
    system: str,
    messages: list[dict],
    max_tokens: int = 4000,
    usage: UsageCollector | None = None,
):
    """Потоковый текстовый ответ модели: yield'ит куски текста по мере генерации.

    ContextVar-коллектор здесь не используется: генератор потребляется вне
    контекста запроса, поэтому расход токенов пишется в явно переданный usage.
    """
    client = get_anthropic_client()
    async with client.messages.stream(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text
        final = await stream.get_final_message()
    if usage is not None:
        usage.input_tokens += int(getattr(final.usage, "input_tokens", 0) or 0)
        usage.output_tokens += int(getattr(final.usage, "output_tokens", 0) or 0)


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
