"""Telegram-канал уведомлений.

Привязка: пользователь получает код в настройках, отправляет боту
`/start <код>` — фоновый опрос getUpdates находит код и сохраняет chat_id.
Без TELEGRAM_BOT_TOKEN канал молча выключен.
"""

import logging
import secrets

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import User

logger = logging.getLogger("app.telegram")

API = "https://api.telegram.org/bot{token}/{method}"


def telegram_enabled() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN)


async def _call(method: str, **params) -> dict | None:
    if not telegram_enabled():
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                API.format(token=settings.TELEGRAM_BOT_TOKEN, method=method),
                json=params,
            )
            data = response.json()
            if not data.get("ok"):
                logger.warning("telegram %s failed: %s", method, data)
                return None
            return data["result"]
    except Exception:
        logger.exception("telegram %s failed", method)
        return None


async def send_telegram(chat_id: str, text: str) -> bool:
    result = await _call("sendMessage", chat_id=chat_id, text=text)
    return result is not None


async def get_bot_username() -> str | None:
    result = await _call("getMe")
    return result.get("username") if result else None


def issue_link_code(user: User) -> str:
    """Одноразовый код привязки; сохраняется на пользователе."""
    code = secrets.token_hex(8)
    user.telegram_link_code = code
    return code


async def poll_link_updates(db: AsyncSession, offset: int | None = None) -> int | None:
    """Один проход getUpdates: ищет `/start <код>` и привязывает chat_id.

    Возвращает следующий offset (или None, если канал выключен/ошибка).
    """
    params: dict = {"timeout": 0, "allowed_updates": ["message"]}
    if offset is not None:
        params["offset"] = offset
    updates = await _call("getUpdates", **params)
    if updates is None:
        return None

    next_offset = offset
    for update in updates:
        next_offset = update["update_id"] + 1
        message = update.get("message") or {}
        text = (message.get("text") or "").strip()
        chat_id = str((message.get("chat") or {}).get("id", ""))
        if not text.startswith("/start") or not chat_id:
            continue
        parts = text.split(maxsplit=1)
        code = parts[1].strip() if len(parts) > 1 else ""
        if not code:
            continue
        user = (
            await db.execute(select(User).where(User.telegram_link_code == code))
        ).scalar_one_or_none()
        if user is None:
            await send_telegram(chat_id, "Код не найден. Получите новый в настройках AI Legal Workspace.")
            continue
        user.telegram_chat_id = chat_id
        user.telegram_link_code = None
        await db.commit()
        await send_telegram(
            chat_id,
            f"Готово, {user.full_name or user.username}! Сюда будут приходить "
            f"уведомления AI Legal Workspace: сроки, согласования, подписи.",
        )
        logger.info("telegram linked for user %s", user.id)
    return next_offset
