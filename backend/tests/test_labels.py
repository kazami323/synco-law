"""Тесты отметок («плашек») на документах и расширенных типов документов."""

CONTRACT = {
    "title": "Договор для проверки отметок",
    "contract_type": "service",
    "counterparty": 'ООО "Контрагент"',
    "content": "1. ПРЕДМЕТ\nИсполнитель оказывает услуги...",
}


async def _create(client, headers, **overrides):
    resp = await client.post(
        "/api/contracts/", json={**CONTRACT, **overrides}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _lawyer_headers(client, admin_headers):
    """Заводит рядового юриста в организации админа (роль по умолчанию)."""
    resp = await client.post(
        "/api/users/",
        json={
            "email": "lw@test.uz",
            "username": "lawyer-user",
            "password": "Secret1234",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    login = await client.post(
        "/api/auth/login", json={"email": "lw@test.uz", "password": "Secret1234"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_set_and_list_label(client, admin_headers):
    contract = await _create(client, admin_headers)

    resp = await client.put(
        f"/api/contracts/{contract['id']}/labels/approved",
        json={"note": "Проверил лично"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "approved"
    assert body["title"] == "Утверждено"
    assert body["actor_type"] == "user"
    assert body["actor_role"] == "admin"
    assert body["note"] == "Проверил лично"

    listing = await client.get(
        f"/api/contracts/{contract['id']}/labels", headers=admin_headers
    )
    assert listing.status_code == 200
    assert [item["kind"] for item in listing.json()] == ["approved"]


async def test_labels_are_returned_with_contract_list(client, admin_headers):
    contract = await _create(client, admin_headers)
    await client.put(
        f"/api/contracts/{contract['id']}/labels/approved", headers=admin_headers
    )

    listing = await client.get("/api/contracts/", headers=admin_headers)
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    assert [label["kind"] for label in items[0]["labels"]] == ["approved"]

    detail = await client.get(
        f"/api/contracts/{contract['id']}", headers=admin_headers
    )
    assert [label["kind"] for label in detail.json()["labels"]] == ["approved"]


async def test_repeated_set_updates_instead_of_duplicating(client, admin_headers):
    contract = await _create(client, admin_headers)
    for note in ("первый раз", "второй раз"):
        resp = await client.put(
            f"/api/contracts/{contract['id']}/labels/approved",
            json={"note": note},
            headers=admin_headers,
        )
        assert resp.status_code == 200

    listing = await client.get(
        f"/api/contracts/{contract['id']}/labels", headers=admin_headers
    )
    labels = listing.json()
    assert len(labels) == 1, "плашка должна обновляться, а не дублироваться"
    assert labels[0]["note"] == "второй раз"


async def test_remove_label(client, admin_headers):
    contract = await _create(client, admin_headers)
    await client.put(
        f"/api/contracts/{contract['id']}/labels/approved", headers=admin_headers
    )

    resp = await client.delete(
        f"/api/contracts/{contract['id']}/labels/approved", headers=admin_headers
    )
    assert resp.status_code == 204

    listing = await client.get(
        f"/api/contracts/{contract['id']}/labels", headers=admin_headers
    )
    assert listing.json() == []

    # Повторное снятие — уже нечего снимать
    again = await client.delete(
        f"/api/contracts/{contract['id']}/labels/approved", headers=admin_headers
    )
    assert again.status_code == 404


async def test_ai_label_cannot_be_set_by_hand(client, admin_headers):
    contract = await _create(client, admin_headers)
    resp = await client.put(
        f"/api/contracts/{contract['id']}/labels/ai_reviewed", headers=admin_headers
    )
    assert resp.status_code == 400
    assert "автомат" in resp.json()["detail"].lower()


async def test_unknown_label_rejected(client, admin_headers):
    contract = await _create(client, admin_headers)
    resp = await client.put(
        f"/api/contracts/{contract['id']}/labels/выдуманная", headers=admin_headers
    )
    assert resp.status_code == 404


async def test_lawyer_cannot_approve_but_can_mark_prepared(client, admin_headers):
    lawyer_headers = await _lawyer_headers(client, admin_headers)
    contract = await _create(client, lawyer_headers, title="Документ юриста")

    denied = await client.put(
        f"/api/contracts/{contract['id']}/labels/approved", headers=lawyer_headers
    )
    assert denied.status_code == 403, "утверждать может только согласующий"

    allowed = await client.put(
        f"/api/contracts/{contract['id']}/labels/prepared", headers=lawyer_headers
    )
    assert allowed.status_code == 200
    assert allowed.json()["actor_role"] == "lawyer"
    assert allowed.json()["actor_role_title"] == "юрист"


async def test_catalogue_reflects_user_rights(client, admin_headers):
    lawyer_headers = await _lawyer_headers(client, admin_headers)

    admin_view = (
        await client.get("/api/labels/catalogue", headers=admin_headers)
    ).json()
    lawyer_view = (
        await client.get("/api/labels/catalogue", headers=lawyer_headers)
    ).json()

    admin_can = {item["kind"] for item in admin_view if item["can_set"]}
    lawyer_can = {item["kind"] for item in lawyer_view if item["can_set"]}

    assert "approved" in admin_can
    assert "approved" not in lawyer_can
    assert "prepared" in lawyer_can
    # Автоматическую плашку не может ставить никто вручную
    assert all(not item["can_set"] for item in admin_view if item["auto_only"])


async def test_new_document_types_accepted(client, admin_headers):
    for doc_type in ("risk_map", "legal_opinion", "contract_review", "other"):
        created = await _create(
            client, admin_headers, contract_type=doc_type, title=f"Документ {doc_type}"
        )
        assert created["contract_type"] == doc_type


async def test_invalid_document_type_rejected(client, admin_headers):
    resp = await client.post(
        "/api/contracts/",
        json={**CONTRACT, "contract_type": "неизвестный_тип"},
        headers=admin_headers,
    )
    assert resp.status_code in (400, 422)
