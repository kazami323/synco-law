"""Тесты workflow согласования: цепочка статусов, роли, отклонение."""

from tests.conftest import register_and_login


async def _make_user(client, admin_headers, email, username, role):
    resp = await client.post(
        "/api/users/",
        json={
            "email": email,
            "username": username,
            "password": "secret123",
            "role": role,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": "secret123"}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _make_contract(client, headers, title="Договор согласования") -> str:
    resp = await client.post(
        "/api/contracts/",
        json={"title": title, "contract_type": "service", "content": "Текст"},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_full_approval_chain(client, admin_headers):
    head = await _make_user(client, admin_headers, "head@test.uz", "head", "head")
    finance = await _make_user(client, admin_headers, "fin@test.uz", "fin", "finance")
    cid = await _make_contract(client, admin_headers)

    # head: юридическое согласование прямо из draft
    resp = await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal",
        json={"comment": "Проверено юротделом"},
        headers=head,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    # финансы
    resp = await client.post(
        f"/api/contracts/{cid}/workflow/approve_finance", json={}, headers=finance
    )
    assert resp.json()["status"] == "approved_finance"

    # head: к подписанию
    resp = await client.post(
        f"/api/contracts/{cid}/workflow/finalize", json={}, headers=head
    )
    assert resp.json()["status"] == "ready_to_sign"

    # админ подписывает (E-IMZO-заглушка)
    resp = await client.post(
        f"/api/contracts/{cid}/workflow/sign", json={}, headers=admin_headers
    )
    assert resp.json()["status"] == "signed"

    detail = (await client.get(f"/api/contracts/{cid}", headers=admin_headers)).json()
    assert detail["status"] == "signed"

    wf = (
        await client.get(f"/api/contracts/{cid}/workflow", headers=admin_headers)
    ).json()
    stages = [h["stage"] for h in wf["history"]]
    assert stages == ["approved", "approved_finance", "ready_to_sign", "signed"]
    assert wf["history"][0]["comment"] == "Проверено юротделом"
    assert all(h["by"] for h in wf["history"])
    assert wf["available_actions"] == []  # из signed переходов нет


async def test_lawyer_cannot_approve(client, admin_headers):
    lawyer = await _make_user(client, admin_headers, "l@test.uz", "l", "lawyer")
    cid = await _make_contract(client, admin_headers)
    resp = await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=lawyer
    )
    assert resp.status_code == 403


async def test_finance_only_from_approved_status(client, admin_headers):
    finance = await _make_user(client, admin_headers, "f2@test.uz", "f2", "finance")
    cid = await _make_contract(client, admin_headers)

    # из draft финансовое согласование недоступно
    resp = await client.post(
        f"/api/contracts/{cid}/workflow/approve_finance", json={}, headers=finance
    )
    assert resp.status_code == 409
    # и юридическое финансам не положено
    resp = await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=finance
    )
    assert resp.status_code == 403


async def test_reject_requires_comment_and_returns_to_draft(client, admin_headers):
    cid = await _make_contract(client, admin_headers)
    await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=admin_headers
    )

    resp = await client.post(
        f"/api/contracts/{cid}/workflow/reject", json={}, headers=admin_headers
    )
    assert resp.status_code == 400  # нет комментария

    resp = await client.post(
        f"/api/contracts/{cid}/workflow/reject",
        json={"comment": "Исправить пени"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "draft"

    wf = (
        await client.get(f"/api/contracts/{cid}/workflow", headers=admin_headers)
    ).json()
    assert wf["history"][-1]["stage"] == "rejected"
    assert wf["history"][-1]["comment"] == "Исправить пени"


async def test_available_actions_by_role(client, admin_headers):
    head = await _make_user(client, admin_headers, "h2@test.uz", "h2", "head")
    finance = await _make_user(client, admin_headers, "f3@test.uz", "f3", "finance")
    cid = await _make_contract(client, admin_headers)

    wf = (await client.get(f"/api/contracts/{cid}/workflow", headers=head)).json()
    assert wf["available_actions"] == ["approve_legal"]  # draft: только юр. шаг

    await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=head
    )
    wf = (await client.get(f"/api/contracts/{cid}/workflow", headers=finance)).json()
    assert set(wf["available_actions"]) == {"approve_finance", "reject"}
    # head из approved ничего согласовать не может (ждём финансы), но может отклонить
    wf = (await client.get(f"/api/contracts/{cid}/workflow", headers=head)).json()
    assert wf["available_actions"] == ["reject"]


async def test_unknown_action_404(client, admin_headers):
    cid = await _make_contract(client, admin_headers)
    resp = await client.post(
        f"/api/contracts/{cid}/workflow/hack", json={}, headers=admin_headers
    )
    assert resp.status_code == 404
