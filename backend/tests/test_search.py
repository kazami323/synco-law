"""Тесты поиска по архиву: SQL-fallback путь (ES в тестах выключен)."""

import pytest

from app.services import search as search_service
from tests.conftest import register_and_login


@pytest.fixture(autouse=True)
def no_elasticsearch(monkeypatch):
    """Тесты детерминированно ходят по SQL-fallback."""

    async def unavailable(**kwargs):
        raise ConnectionError("ES down in tests")

    monkeypatch.setattr(search_service, "search_contracts", unavailable)


async def _seed(client, headers):
    docs = [
        {
            "title": "Договор аренды склада",
            "contract_type": "lease",
            "counterparty": "ООО Логистик",
            "content": "Арендодатель передаёт склад площадью 500 кв.м. в Ташкенте.",
        },
        {
            "title": "Договор поставки серверов",
            "contract_type": "purchase",
            "counterparty": "ООО ТехПром",
            "content": "Поставка 10 серверов Dell с гарантией 36 месяцев.",
        },
        {
            "title": "NDA с подрядчиком",
            "contract_type": "nda",
            "counterparty": "ИП Каримов",
            "content": "Стороны обязуются не разглашать условия сотрудничества.",
        },
    ]
    for doc in docs:
        resp = await client.post("/api/contracts/", json=doc, headers=headers)
        assert resp.status_code == 201


async def test_search_by_text_with_snippet(client, admin_headers):
    await _seed(client, admin_headers)
    resp = await client.get("/api/search/?q=склад", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["engine"] == "sql"
    assert data["total"] == 1
    item = data["items"][0]
    assert item["title"] == "Договор аренды склада"
    assert "<mark>склад</mark>" in item["snippets"][0]


async def test_search_filters(client, admin_headers):
    await _seed(client, admin_headers)

    by_type = (
        await client.get("/api/search/?contract_type=nda", headers=admin_headers)
    ).json()
    assert by_type["total"] == 1
    assert by_type["items"][0]["contract_type"] == "nda"

    by_counterparty = (
        await client.get("/api/search/?counterparty=ТехПром", headers=admin_headers)
    ).json()
    assert by_counterparty["total"] == 1

    empty = (
        await client.get("/api/search/?q=блокчейн", headers=admin_headers)
    ).json()
    assert empty["total"] == 0


async def test_search_escapes_html_in_snippets(client, admin_headers):
    resp = await client.post(
        "/api/contracts/",
        json={
            "title": "XSS проверка",
            "contract_type": "other",
            "content": 'Пункт <script>alert("x")</script> про оплату аванса.',
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201

    data = (
        await client.get("/api/search/?q=оплату", headers=admin_headers)
    ).json()
    snippet = data["items"][0]["snippets"][0]
    assert "<script>" not in snippet
    assert "&lt;script&gt;" in snippet
    assert "<mark>оплату</mark>" in snippet


async def test_lawyer_sees_only_own_in_search(client, admin_headers):
    await _seed(client, admin_headers)

    resp = await client.post(
        "/api/users/",
        json={
            "email": "law@test.uz",
            "username": "law",
            "password": "Secret1234",
            "role": "lawyer",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201
    login = await client.post(
        "/api/auth/login", json={"email": "law@test.uz", "password": "Secret1234"}
    )
    lawyer = {"Authorization": f"Bearer {login.json()['access_token']}"}

    mine = await client.post(
        "/api/contracts/",
        json={"title": "Мой договор юриста", "contract_type": "service"},
        headers=lawyer,
    )
    assert mine.status_code == 201

    data = (await client.get("/api/search/", headers=lawyer)).json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Мой договор юриста"


async def test_search_requires_org(client):
    headers = await register_and_login(client, "solo@test.uz", "solo")
    resp = await client.get("/api/search/?q=test", headers=headers)
    assert resp.status_code == 400
