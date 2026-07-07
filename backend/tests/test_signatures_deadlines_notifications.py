from datetime import date, timedelta

BASE_CONTRACT = {
    "title": "Contract for Weeks 11-12",
    "contract_type": "service",
    "counterparty": "Acme LLC",
    "content": "Base contract text",
    "amount": 1000,
    "currency": "UZS",
}


async def _create_contract(client, headers, **overrides) -> dict:
    resp = await client.post(
        "/api/contracts/",
        json={**BASE_CONTRACT, **overrides},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _move_to_ready_to_sign(client, headers, contract_id: str) -> None:
    for action in ("approve_legal", "approve_finance", "finalize"):
        resp = await client.post(
            f"/api/contracts/{contract_id}/workflow/{action}",
            json={},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text


async def test_sign_request_requires_ready_to_sign(client, admin_headers):
    contract = await _create_contract(client, admin_headers)
    resp = await client.post(
        f"/api/contracts/{contract['id']}/sign-request",
        json={},
        headers=admin_headers,
    )
    assert resp.status_code == 409


async def test_sign_request_and_confirm_stores_eimzo_stub(client, admin_headers):
    contract = await _create_contract(client, admin_headers)
    await _move_to_ready_to_sign(client, admin_headers, contract["id"])

    request_resp = await client.post(
        f"/api/contracts/{contract['id']}/sign-request",
        json={},
        headers=admin_headers,
    )
    assert request_resp.status_code == 200, request_resp.text
    sign_request = request_resp.json()
    assert len(sign_request["hash"]) == 64
    assert sign_request["request_id"]

    confirm_resp = await client.post(
        f"/api/contracts/{contract['id']}/sign-confirm",
        json={"request_id": sign_request["request_id"], "pin": "123456"},
        headers=admin_headers,
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    confirmed = confirm_resp.json()
    assert confirmed["signature"].startswith("EIMZO-STUB-SIGNATURE")
    assert confirmed["certificate_thumbprint"]
    assert confirmed["timestamp"]

    detail = (
        await client.get(f"/api/contracts/{contract['id']}", headers=admin_headers)
    ).json()
    assert detail["status"] == "signed"
    assert detail["signature"].startswith("EIMZO-STUB-SIGNATURE")
    assert detail["signature_timestamp"]
    assert detail["certificate_thumbprint"] == confirmed["certificate_thumbprint"]


async def test_sign_confirm_requires_pending_request(client, admin_headers):
    contract = await _create_contract(client, admin_headers)
    await _move_to_ready_to_sign(client, admin_headers, contract["id"])

    resp = await client.post(
        f"/api/contracts/{contract['id']}/sign-confirm",
        json={},
        headers=admin_headers,
    )
    assert resp.status_code == 404


async def test_sign_confirm_rejects_changed_contract_hash(client, admin_headers):
    contract = await _create_contract(client, admin_headers)
    await _move_to_ready_to_sign(client, admin_headers, contract["id"])

    request_resp = await client.post(
        f"/api/contracts/{contract['id']}/sign-request",
        json={},
        headers=admin_headers,
    )
    sign_request = request_resp.json()

    update_resp = await client.put(
        f"/api/contracts/{contract['id']}",
        json={"content": "Changed after sign request"},
        headers=admin_headers,
    )
    assert update_resp.status_code == 200, update_resp.text

    confirm_resp = await client.post(
        f"/api/contracts/{contract['id']}/sign-confirm",
        json={"request_id": sign_request["request_id"]},
        headers=admin_headers,
    )
    assert confirm_resp.status_code == 409


async def test_deadlines_are_parsed_from_contract_text(client, admin_headers):
    target = date.today() + timedelta(days=5)
    contract = await _create_contract(
        client,
        admin_headers,
        content=f"Payment section: оплата до {target.isoformat()} по счету.",
    )

    resp = await client.get(
        f"/api/contracts/{contract['id']}/deadlines",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    deadlines = resp.json()
    assert len(deadlines) == 1
    assert deadlines[0]["deadline_date"] == target.isoformat()
    assert deadlines[0]["type"] == "payment"
    assert deadlines[0]["days_left"] == 5


async def test_manual_deadline_creates_notification_and_mark_read(client, admin_headers):
    target = date.today() + timedelta(days=3)
    contract = await _create_contract(client, admin_headers)

    resp = await client.post(
        f"/api/contracts/{contract['id']}/deadlines",
        json={"deadline_date": target.isoformat(), "type": "delivery"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["days_left"] == 3

    unread = (
        await client.get("/api/notifications/unread-count", headers=admin_headers)
    ).json()
    assert unread["count"] == 1

    notifications = (
        await client.get("/api/notifications/?limit=10", headers=admin_headers)
    ).json()
    assert len(notifications) == 1
    assert notifications[0]["read_at"] is None
    assert "delivery" in notifications[0]["text"]

    read_resp = await client.patch(
        f"/api/notifications/{notifications[0]['id']}/read",
        headers=admin_headers,
    )
    assert read_resp.status_code == 200, read_resp.text
    assert read_resp.json()["read_at"] is not None

    unread = (
        await client.get("/api/notifications/unread-count", headers=admin_headers)
    ).json()
    assert unread["count"] == 0


async def test_far_future_deadline_does_not_create_notification(client, admin_headers):
    target = date.today() + timedelta(days=30)
    contract = await _create_contract(client, admin_headers)

    resp = await client.post(
        f"/api/contracts/{contract['id']}/deadlines",
        json={"deadline_date": target.isoformat(), "type": "payment"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text

    unread = (
        await client.get("/api/notifications/unread-count", headers=admin_headers)
    ).json()
    assert unread["count"] == 0


async def test_dashboard_upcoming_deadlines_count_distinct_contracts(client, admin_headers):
    soon = date.today() + timedelta(days=2)
    later = date.today() + timedelta(days=20)
    contract = await _create_contract(client, admin_headers)
    for deadline_date in (soon, soon + timedelta(days=1), later):
        resp = await client.post(
            f"/api/contracts/{contract['id']}/deadlines",
            json={"deadline_date": deadline_date.isoformat(), "type": "report"},
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text

    metrics = (
        await client.get("/api/dashboard/metrics", headers=admin_headers)
    ).json()
    assert metrics["upcoming_deadlines_count"] == 1
    assert len(metrics["upcoming_deadlines"]) == 2


async def test_upcoming_deadlines_endpoint_orders_by_date(client, admin_headers):
    later_contract = await _create_contract(
        client, admin_headers, title="Later deadline"
    )
    sooner_contract = await _create_contract(
        client, admin_headers, title="Sooner deadline"
    )

    await client.post(
        f"/api/contracts/{later_contract['id']}/deadlines",
        json={
            "deadline_date": (date.today() + timedelta(days=6)).isoformat(),
            "type": "delivery",
        },
        headers=admin_headers,
    )
    await client.post(
        f"/api/contracts/{sooner_contract['id']}/deadlines",
        json={
            "deadline_date": (date.today() + timedelta(days=1)).isoformat(),
            "type": "payment",
        },
        headers=admin_headers,
    )

    resp = await client.get(
        "/api/contracts/upcoming-deadlines?limit=5",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [row["contract_title"] for row in rows[:2]] == [
        "Sooner deadline",
        "Later deadline",
    ]


# ---------- Фиксы ревью: мусорные даты, окно уведомлений, read-all ----------

def test_parser_ignores_clause_numbers_and_junk_years():
    from app.services.deadlines import extract_deadlines_from_text

    text = (
        "Согласно пункту 1.2.3 настоящего договора и разделу 4.5.6 "
        "оплата производится до 15.09.2026. Версия документа 2.1.10."
    )
    parsed = extract_deadlines_from_text(text)
    assert [item["deadline_date"].isoformat() for item in parsed] == ["2026-09-15"]


def test_parser_rejects_implausible_years():
    from app.services.deadlines import extract_deadlines_from_text

    parsed = extract_deadlines_from_text("срок до 01.01.1999 и до 5.5.3000")
    assert parsed == []


async def test_old_deadline_creates_no_notification(client, admin_headers):
    contract = await _create_contract(client, admin_headers, title="Old deadline")
    old = date.today() - timedelta(days=120)
    resp = await client.post(
        f"/api/contracts/{contract['id']}/deadlines",
        json={"deadline_date": old.isoformat(), "type": "payment"},
        headers=admin_headers,
    )
    assert resp.status_code == 201

    notifications = (
        await client.get("/api/notifications/", headers=admin_headers)
    ).json()
    assert not any("Old deadline" in n["text"] for n in notifications)


async def test_ancient_date_in_text_not_parsed_as_deadline(client, admin_headers):
    contract = await _create_contract(
        client,
        admin_headers,
        title="Legacy date in text",
        content="Договор заключён 15.01.2020 и действует до 01.10.2026.",
    )
    deadlines = (
        await client.get(
            f"/api/contracts/{contract['id']}/deadlines", headers=admin_headers
        )
    ).json()
    dates = [d["deadline_date"] for d in deadlines]
    assert "2020-01-15" not in dates
    assert "2026-10-01" in dates


async def test_read_all_notifications(client, admin_headers):
    contract = await _create_contract(client, admin_headers, title="Read all test")
    for offset in (1, 2):
        await client.post(
            f"/api/contracts/{contract['id']}/deadlines",
            json={
                "deadline_date": (date.today() + timedelta(days=offset)).isoformat(),
                "type": "payment",
            },
            headers=admin_headers,
        )

    before = (
        await client.get("/api/notifications/unread-count", headers=admin_headers)
    ).json()
    assert before["count"] > 0

    resp = await client.post("/api/notifications/read-all", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["marked"] == before["count"]

    after = (
        await client.get("/api/notifications/unread-count", headers=admin_headers)
    ).json()
    assert after["count"] == 0


async def test_sign_confirm_with_real_pkcs7(client, admin_headers):
    """Подпись реальным PKCS#7 от E-IMZO: сохраняется как есть, тип eimzo."""
    contract = await _create_contract(client, admin_headers, title="E-IMZO real")
    await _move_to_ready_to_sign(client, admin_headers, contract["id"])
    request_resp = await client.post(
        f"/api/contracts/{contract['id']}/sign-request",
        json={},
        headers=admin_headers,
    )
    resp = await client.post(
        f"/api/contracts/{contract['id']}/sign-confirm",
        json={
            "request_id": request_resp.json()["request_id"],
            "signature": "MIIC...FAKE_PKCS7_BASE64",
            "certificate": "cn=FIRSOV DANIL,o=OOO Test,serialnumber=AB123",
            "certificate_thumbprint": "AB123456",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["signature"] == "MIIC...FAKE_PKCS7_BASE64"
    assert resp.json()["certificate_thumbprint"] == "AB123456"

    detail = (
        await client.get(f"/api/contracts/{contract['id']}", headers=admin_headers)
    ).json()
    assert detail["status"] == "signed"
    assert detail["certificate_thumbprint"] == "AB123456"


async def test_sign_confirm_rejected_by_dsv(client, admin_headers, monkeypatch):
    """Если настроен DSV и он отверг подпись — 400, контракт не подписан."""
    from app.api import contracts as contracts_api

    async def dsv_reject(pkcs7: str):
        return False

    monkeypatch.setattr(contracts_api, "verify_pkcs7_via_dsv", dsv_reject)

    contract = await _create_contract(client, admin_headers, title="DSV reject")
    await _move_to_ready_to_sign(client, admin_headers, contract["id"])
    await client.post(
        f"/api/contracts/{contract['id']}/sign-request", json={}, headers=admin_headers
    )
    resp = await client.post(
        f"/api/contracts/{contract['id']}/sign-confirm",
        json={"signature": "BAD_PKCS7"},
        headers=admin_headers,
    )
    assert resp.status_code == 400

    detail = (
        await client.get(f"/api/contracts/{contract['id']}", headers=admin_headers)
    ).json()
    assert detail["status"] == "ready_to_sign"
