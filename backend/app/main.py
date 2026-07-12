import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import (
    agents,
    auth,
    chat_sessions,
    contracts,
    dashboard,
    legal,
    notifications,
    organizations,
    projects,
    search,
    users,
    workflow,
)
from app.core.config import settings
from app.db.base import engine
from app.services.background import start_background_tasks
from app.services.legal_search import ensure_index as ensure_legal_index
from app.services.search import ensure_index

settings.validate_runtime()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_index()  # без ES поиск работает через SQL fallback
    await ensure_legal_index()
    tasks = start_background_tasks() if settings.RUN_BACKGROUND_JOBS else []
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
app.include_router(chat_sessions.router)
app.include_router(dashboard.router)
app.include_router(legal.router)
app.include_router(notifications.router)
app.include_router(workflow.router)
app.include_router(search.router)


@app.get("/health", tags=["system"])
async def health() -> dict:
    """Readiness check: returns 503 when the database is unavailable."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "database": "ok",
    }


@app.get("/health/live", tags=["system"])
async def liveness() -> dict:
    return {"status": "ok", "version": settings.APP_VERSION}
