import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import agents, auth, contracts, dashboard, notifications, organizations, users, workflow
from app.core.config import settings
from app.db.base import async_session_factory, engine
from app.services.notifications import create_deadline_notifications

settings.validate_runtime()

logger = logging.getLogger("app.deadlines")


async def _deadline_notification_loop() -> None:
    while True:
        try:
            async with async_session_factory() as session:
                created = await create_deadline_notifications(session)
                await session.commit()
                if created:
                    logger.info("deadline notifications created: %s", created)
        except Exception:
            logger.exception("deadline notification loop failed")
        await asyncio.sleep(24 * 60 * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_deadline_notification_loop())
    app.state.deadline_notification_task = task
    try:
        yield
    finally:
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
app.include_router(agents.router)
app.include_router(dashboard.router)
app.include_router(notifications.router)
app.include_router(workflow.router)


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
