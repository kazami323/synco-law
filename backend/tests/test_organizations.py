"""Тесты организаций: создание, привязка создателя, права на редактирование."""

from tests.conftest import register_and_login


async def test_create_organization_promotes_creator_to_admin(client):
    headers = await register_and_login(client, email="org@test.uz", username="orguser")

    resp = await client.post(
        "/api/organizations/",
        json={"name": "ООО Ромашка", "email": "info@romashka.uz"},
        headers=headers,
    )
    assert resp.status_code == 201
    org = resp.json()
    assert org["name"] == "ООО Ромашка"
    assert org["country"] == "Uzbekistan"

    me = (await client.get("/api/auth/me", headers=headers)).json()
    assert me["role"] == "admin"
    assert me["organization_id"] == org["id"]


async def test_cannot_create_second_organization(client, admin_headers):
    resp = await client.post(
        "/api/organizations/", json={"name": "Вторая"}, headers=admin_headers
    )
    assert resp.status_code == 409


async def test_org_me_without_organization(client):
    headers = await register_and_login(client, email="noorg@test.uz", username="noorg")
    assert (await client.get("/api/organizations/me", headers=headers)).status_code == 404


async def test_update_organization(client, admin_headers):
    resp = await client.put(
        "/api/organizations/me",
        json={"phone": "+998 71 200-00-00"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["phone"] == "+998 71 200-00-00"
    assert resp.json()["name"] == "ООО Тест"  # остальные поля не тронуты


async def test_lawyer_cannot_update_organization(client, admin_headers):
    # админ создаёт юриста в своей организации
    resp = await client.post(
        "/api/users/",
        json={"email": "lw@test.uz", "username": "lw", "password": "secret123"},
        headers=admin_headers,
    )
    assert resp.status_code == 201

    lawyer_login = await client.post(
        "/api/auth/login", json={"email": "lw@test.uz", "password": "secret123"}
    )
    lawyer_headers = {
        "Authorization": f"Bearer {lawyer_login.json()['access_token']}"
    }
    resp = await client.put(
        "/api/organizations/me", json={"name": "Хак"}, headers=lawyer_headers
    )
    assert resp.status_code == 403
