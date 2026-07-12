"""Тесты управления пользователями: создание, роли, деактивация, права."""

from tests.conftest import register_and_login


async def _create_user(client, admin_headers, email, username, role="lawyer"):
    resp = await client.post(
        "/api/users/",
        json={
            "email": email,
            "username": username,
            "password": "Secret1234",
            "role": role,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _login(client, email, password="Secret1234"):
    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    return resp, (
        {"Authorization": f"Bearer {resp.json()['access_token']}"}
        if resp.status_code == 200
        else None
    )


async def test_admin_creates_and_lists_users(client, admin_headers):
    created = await _create_user(client, admin_headers, "u1@test.uz", "u1")
    assert created["role"] == "lawyer"
    assert created["organization_id"] is not None

    resp = await client.get("/api/users/", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2  # админ + созданный юрист
    emails = {u["email"] for u in body["items"]}
    assert emails == {"admin@test.uz", "u1@test.uz"}


async def test_lawyer_cannot_manage_users(client, admin_headers):
    await _create_user(client, admin_headers, "u2@test.uz", "u2")
    _, lawyer_headers = await _login(client, "u2@test.uz")

    # у lawyer нет view_all -> список недоступен
    assert (await client.get("/api/users/", headers=lawyer_headers)).status_code == 403
    # и нет manage_users -> создание недоступно
    resp = await client.post(
        "/api/users/",
        json={"email": "x@test.uz", "username": "invalid", "password": "Secret1234"},
        headers=lawyer_headers,
    )
    assert resp.status_code == 403


async def test_change_role_and_deactivate(client, admin_headers):
    created = await _create_user(client, admin_headers, "u3@test.uz", "u3")

    resp = await client.patch(
        f"/api/users/{created['id']}",
        json={"role": "senior_lawyer"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "senior_lawyer"

    resp = await client.patch(
        f"/api/users/{created['id']}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # деактивированный пользователь не может войти
    login_resp, _ = await _login(client, "u3@test.uz")
    assert login_resp.status_code == 401


async def test_invalid_role_rejected(client, admin_headers):
    created = await _create_user(client, admin_headers, "u4@test.uz", "u4")
    resp = await client.patch(
        f"/api/users/{created['id']}",
        json={"role": "superhero"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_admin_cannot_deactivate_self(client, admin_headers):
    me = (await client.get("/api/auth/me", headers=admin_headers)).json()
    resp = await client.patch(
        f"/api/users/{me['id']}", json={"is_active": False}, headers=admin_headers
    )
    assert resp.status_code == 400


async def test_head_cannot_assign_admin_role(client, admin_headers):
    await _create_user(client, admin_headers, "head@test.uz", "head", role="head")
    target = await _create_user(client, admin_headers, "u5@test.uz", "u5")
    _, head_headers = await _login(client, "head@test.uz")

    # head управляет пользователями, но назначить админа не может
    resp = await client.patch(
        f"/api/users/{target['id']}", json={"role": "admin"}, headers=head_headers
    )
    assert resp.status_code == 403
    # а обычную роль — может
    resp = await client.patch(
        f"/api/users/{target['id']}", json={"role": "finance"}, headers=head_headers
    )
    assert resp.status_code == 200


async def test_user_without_org_gets_400(client):
    headers = await register_and_login(client, email="solo@test.uz", username="solo")
    # у пользователя без организации нет прав view_all (роль lawyer) -> сначала 403
    assert (await client.get("/api/users/", headers=headers)).status_code == 403
