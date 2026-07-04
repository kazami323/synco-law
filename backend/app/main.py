from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import agents, auth, contracts, dashboard, users
from app.core.config import settings
from app.db.base import engine

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
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
app.include_router(users.router)
app.include_router(contracts.router)
app.include_router(agents.router)
app.include_router(dashboard.router)


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
