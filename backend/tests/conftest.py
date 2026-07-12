"""Фикстуры тестов: отдельная БД legal_workspace_test, чистая схема на каждый тест."""

import psycopg2
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base, get_db
from app.main import app

TEST_DB_NAME = "legal_workspace_test"
TEST_DB_URL = settings.DATABASE_URL.rsplit("/", 1)[0] + "/" + TEST_DB_NAME


def _ensure_test_db() -> None:
    """Создаёт тестовую базу, если её ещё нет (одноразово, синхронно)."""
    dsn = settings.DATABASE_URL.replace("+asyncpg", "").rsplit("/", 1)[0] + "/postgres"
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,))
        if cur.fetchone() is None:
            cur.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    conn.close()


@pytest.fixture(autouse=True)
def _no_search_indexing(monkeypatch):
    # Redis rate limits intentionally survive between production requests.
    # Tests recreate the database per case and must not share those counters.
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")

    """Тесты не должны писать в боевой Elasticsearch-индекс."""

    async def noop(contract) -> None:
        return None

    monkeypatch.setattr("app.services.search.index_contract", noop)


@pytest.fixture
async def db_factory():
    """Пересоздаёт схему в тестовой БД и отдаёт фабрику сессий."""
    _ensure_test_db()
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def client(db_factory):
    """HTTP-клиент к приложению с подменённой БД."""

    async def override_get_db():
        async with db_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def register_and_login(
    client: AsyncClient,
    email: str = "user@test.uz",
    username: str = "user",
    password: str = "password123",
) -> dict:
    """Регистрирует пользователя и возвращает заголовки с Bearer-токеном."""
    resp = await client.post(
        "/api/auth/register",
        json={"email": email, "username": username, "password": password},
    )
    assert resp.status_code == 201, resp.text
    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
async def admin_headers(client):
    """Пользователь, создавший организацию (автоматически admin)."""
    headers = await register_and_login(
        client, email="admin@test.uz", username="admin"
    )
    resp = await client.post(
        "/api/organizations/", json={"name": "ООО Тест"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return headers
