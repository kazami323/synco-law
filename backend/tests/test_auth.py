"""Тесты аутентификации: регистрация, логин, JWT, аудит."""

from sqlalchemy import func, select

from app.db.models import AuditLog
from tests.conftest import register_and_login


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_register_and_login_flow(client):
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": "danil@test.uz",
            "username": "danil",
            "password": "secret123",
            "full_name": "Данил Фирсов",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "danil@test.uz"
    assert body["role"] == "lawyer"  # роль по умолчанию
    assert body["organization_id"] is None

    resp = await client.post(
        "/api/auth/login", json={"email": "danil@test.uz", "password": "secret123"}
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    resp = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["username"] == "danil"


async def test_register_duplicate_email(client):
    payload = {"email": "dup@test.uz", "username": "dup1", "password": "secret123"}
    assert (await client.post("/api/auth/register", json=payload)).status_code == 201
    payload["username"] = "dup2"
    resp = await client.post("/api/auth/register", json=payload)
    assert resp.status_code == 409


async def test_login_wrong_password(client):
    await register_and_login(client, email="wp@test.uz", username="wp")
    resp = await client.post(
        "/api/auth/login", json={"email": "wp@test.uz", "password": "wrong-password"}
    )
    assert resp.status_code == 401


async def test_me_requires_token(client):
    assert (await client.get("/api/auth/me")).status_code == 401
    resp = await client.get(
        "/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"}
    )
    assert resp.status_code == 401


async def test_register_and_login_write_audit(client, db_factory):
    await register_and_login(client, email="audit@test.uz", username="audit")
    async with db_factory() as session:
        for action in ("user_registered", "user_login"):
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(AuditLog)
                    .where(AuditLog.action == action)
                )
            ).scalar_one()
            assert count == 1, f"expected one {action} audit row"
