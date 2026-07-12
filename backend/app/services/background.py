"""Background schedules run by a single worker process."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.db.base import async_session_factory
from app.services.legal_refresh import refresh_legal_sources
from app.services.notifications import create_deadline_notifications
from app.services.notifications import deliver as notify_deliver
from app.services.telegram import poll_link_updates, telegram_enabled

logger = logging.getLogger("app.background")


async def deadline_notification_loop() -> None:
    while True:
        try:
            async with async_session_factory() as session:
                created = await create_deadline_notifications(session)
                await session.commit()
                for recipient, text in created:
                    await notify_deliver(recipient, text)
        except Exception:
            logger.exception("deadline notification loop failed")
        await asyncio.sleep(24 * 60 * 60)


async def telegram_link_loop() -> None:
    if not telegram_enabled():
        return
    offset: int | None = None
    while True:
        try:
            async with async_session_factory() as session:
                offset = await poll_link_updates(session, offset)
        except Exception:
            logger.exception("telegram link loop failed")
        await asyncio.sleep(15)


async def legal_refresh_loop() -> None:
    if not settings.LEGAL_REFRESH_ENABLED:
        return
    while True:
        try:
            async with async_session_factory() as session:
                await refresh_legal_sources(session, refresh_html=True)
        except Exception:
            logger.exception("legal source refresh failed")
        await asyncio.sleep(max(settings.LEGAL_REFRESH_INTERVAL_HOURS, 1) * 60 * 60)


def start_background_tasks() -> list[asyncio.Task]:
    return [
        asyncio.create_task(deadline_notification_loop()),
        asyncio.create_task(telegram_link_loop()),
        asyncio.create_task(legal_refresh_loop()),
    ]


async def run_worker() -> None:
    tasks = start_background_tasks()
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
