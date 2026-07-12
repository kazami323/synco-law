"""Тесты проектов (дел): CRUD, договоры внутри проекта, изоляция
организаций, права."""

from tests.conftest import register_and_login


async def _create_project(http, headers, **fields):
    resp = await http.post(
        "/api/projects/", json={"name": "Проект1", **fields}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_project_crud_and_counts(client, admin_headers):
    project = await _create_project(
        client,
        admin_headers,
        name="Сопровождение сделки",
        client="ООО Пахтакор",
        description="Заказ на юрсопровождение",
    )
    assert project["status"] == "active"
    assert project["contracts_count"] == 0

    # договор внутри проекта
    resp = await client.post(
        "/api/contracts/",
        json={
            "title": "Договор поставки",
            "contract_type": "purchase",
            "content": "Текст",
            "project_id": project["id"],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["project_id"] == project["id"]

    # счётчик в списке и деталях
    projects = (await client.get("/api/projects/", headers=admin_headers)).json()
    assert projects[0]["contracts_count"] == 1
    detail = (
        await client.get(f"/api/projects/{project['id']}", headers=admin_headers)
    ).json()
    assert detail["contracts_count"] == 1

    # фильтр контрактов по проекту
    listing = (
        await client.get(
            f"/api/contracts/?project_id={project['id']}", headers=admin_headers
        )
    ).json()
    assert listing["total"] == 1
    assert listing["items"][0]["title"] == "Договор поставки"

    # контракт без проекта в фильтр не попадает
    await client.post(
        "/api/contracts/",
        json={"title": "Вне проекта", "contract_type": "nda", "content": "Т"},
        headers=admin_headers,
    )
    listing = (
        await client.get(
            f"/api/contracts/?project_id={project['id']}", headers=admin_headers
        )
    ).json()
    assert listing["total"] == 1


async def test_project_update_and_close(client, admin_headers):
    project = await _create_project(client, admin_headers, name="Старое имя")

    resp = await client.patch(
        f"/api/projects/{project['id']}",
        json={"name": "Новое имя", "status": "closed"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Новое имя"
    assert body["status"] == "closed"

    resp = await client.patch(
        f"/api/projects/{project['id']}",
        json={"status": "nonsense"},
        headers=admin_headers,
    )
    assert resp.status_code == 400

    # фильтр по статусу
    active = (
        await client.get("/api/projects/?status_filter=active", headers=admin_headers)
    ).json()
    assert all(p["status"] == "active" for p in active)


async def test_contract_with_alien_project_rejected(client, admin_headers):
    """project_id чужой организации (или несуществующий) — 404."""
    resp = await client.post(
        "/api/contracts/",
        json={
            "title": "Х",
            "contract_type": "nda",
            "content": "Т",
            "project_id": "00000000-0000-0000-0000-000000000001",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 404


async def test_projects_isolated_between_orgs(client, admin_headers):
    project = await _create_project(client, admin_headers, name="Секретный")

    other = await register_and_login(
        client, email="other@org.uz", username="otherorg"
    )
    resp = await client.post(
        "/api/organizations/", json={"name": "Другая фирма"}, headers=other
    )
    assert resp.status_code == 201, resp.text
    # заново логинимся: токен мог быть выдан до появления организации
    resp = await client.post(
        "/api/auth/login", json={"email": "other@org.uz", "password": "password123"}
    )
    other = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    listing = (await client.get("/api/projects/", headers=other)).json()
    assert listing == []
    resp = await client.get(f"/api/projects/{project['id']}", headers=other)
    assert resp.status_code == 404


async def test_external_cannot_create_project(client, admin_headers):
    resp = await client.post(
        "/api/users/",
        json={
            "email": "ext@p.uz",
            "username": "extp",
            "password": "Secret1234",
            "role": "external",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    resp = await client.post(
        "/api/auth/login", json={"email": "ext@p.uz", "password": "Secret1234"}
    )
    ext = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    resp = await client.post(
        "/api/projects/", json={"name": "Нельзя"}, headers=ext
    )
    assert resp.status_code == 403
    # но список проектов видит
    resp = await client.get("/api/projects/", headers=ext)
    assert resp.status_code == 200
