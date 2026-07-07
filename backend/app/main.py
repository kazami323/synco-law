import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import (
    agents,
    auth,
    contracts,
    dashboard,
    notifications,
    organizations,
    projects,
    search,
    users,
    workflow,
)
from app.core.config import settings
from app.db.base import async_session_factory, engine
from app.services.notifications import create_deadline_notifications
from app.services.notifications import deliver as notify_deliver
from app.services.search import ensure_index
from app.services.telegram import poll_link_updates, telegram_enabled

settings.validate_runtime()

logger = logging.getLogger("app.deadlines")


async def _deadline_notification_loop() -> None:
    while True:
        try:
            async with async_session_factory() as session:
                created = await create_deadline_notifications(session)
                await session.commit()
                for recipient, text in created:
                    await notify_deliver(recipient, text)
                if created:
                    logger.info("deadline notifications created: %s", len(created))
        except Exception:
            logger.exception("deadline notification loop failed")
        await asyncio.sleep(24 * 60 * 60)


async def _telegram_link_loop() -> None:
    """Опрос Telegram getUpdates для привязки аккаунтов (если задан токен)."""
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_index()  # без ES поиск работает через SQL fallback
    tasks = [
        asyncio.create_task(_deadline_notification_loop()),
        asyncio.create_task(_telegram_link_loop()),
    ]
    app.state.background_tasks = tasks
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    description="CLM-платформа с AI-агентами для юридических отделов (Узбекистан)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(users.router)
app.include_router(contracts.router)
app.include_router(projects.router)
app.include_router(agents.router)
app.include_router(dashboard.router)
app.include_router(notifications.router)
app.include_router(workflow.router)
app.include_router(search.router)


@app.get("/health", tags=["system"])
async def health() -> dict:
    """Проверка живости сервиса и подключения к БД."""
    db_status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "unavailable"
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "database": db_status,
    }
