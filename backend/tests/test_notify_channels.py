"""Тесты каналов уведомлений: workflow-события, email/telegram (моки),
привязка Telegram."""

import pytest

from app.services import notifications as notify_service
from app.services import telegram as telegram_service


@pytest.fixture
def sent(monkeypatch):
    """Перехватывает доставку в email/telegram."""
    box = {"email": [], "telegram": []}

    async def fake_email(to, subject, body):
        box["email"].append((to, subject, body))
        return True

    async def fake_tg(chat_id, text):
        box["telegram"].append((chat_id, text))
        return True

    monkeypatch.setattr(notify_service, "send_email", fake_email)
    monkeypatch.setattr(notify_service, "send_telegram", fake_tg)
    return box


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


async def test_workflow_notifies_author_and_next_role(client, admin_headers, sent):
    lawyer = await _make_user(client, admin_headers, "l@n.uz", "ln", "lawyer")
    finance = await _make_user(client, admin_headers, "f@n.uz", "fn", "finance")

    # юрист создаёт контракт
    resp = await client.post(
        "/api/contracts/",
        json={"title": "Договор юриста", "contract_type": "service", "content": "Т"},
        headers=lawyer,
    )
    cid = resp.json()["id"]

    # админ согласует юридически → автор получает уведомление,
    # финансисты — приглашение на следующий шаг
    resp = await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal",
        json={"comment": "ок"},
        headers=admin_headers,
    )
    assert resp.status_code == 200

    lawyer_notifications = (
        await client.get("/api/notifications/", headers=lawyer)
    ).json()
    assert any(
        "юридически согласован" in n["text"] for n in lawyer_notifications
    ), lawyer_notifications

    finance_notifications = (
        await client.get("/api/notifications/", headers=finance)
    ).json()
    assert any(
        "финансовое согласование" in n["text"] for n in finance_notifications
    ), finance_notifications

    # email ушёл автору и финансисту (мок)
    emails_to = [e[0] for e in sent["email"]]
    assert "l@n.uz" in emails_to
    assert "f@n.uz" in emails_to


async def test_reject_notifies_author_with_comment(client, admin_headers, sent):
    lawyer = await _make_user(client, admin_headers, "l2@n.uz", "l2n", "lawyer")
    resp = await client.post(
        "/api/contracts/",
        json={"title": "На отклонение", "contract_type": "nda", "content": "Т"},
        headers=lawyer,
    )
    cid = resp.json()["id"]
    await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=admin_headers
    )
    await client.post(
        f"/api/contracts/{cid}/workflow/reject",
        json={"comment": "Поправить сроки"},
        headers=admin_headers,
    )

    notifications = (await client.get("/api/notifications/", headers=lawyer)).json()
    assert any(
        "отклонён" in n["text"] and "Поправить сроки" in n["text"]
        for n in notifications
    ), notifications


async def test_telegram_link_flow(client, admin_headers, monkeypatch, db_factory):
    # без токена — 503 с подсказкой
    resp = await client.post("/api/notifications/telegram/link", headers=admin_headers)
    assert resp.status_code == 503

    # с токеном — код выдаётся, поллинг привязывает chat_id
    monkeypatch.setattr(telegram_service.settings, "TELEGRAM_BOT_TOKEN", "test-token")

    async def fake_call(method, **params):
        if method == "getMe":
            return {"username": "legal_test_bot"}
        if method == "sendMessage":
            return {"ok": True}
        return None

    monkeypatch.setattr(telegram_service, "_call", fake_call)

    resp = await client.post("/api/notifications/telegram/link", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["bot_username"] == "legal_test_bot"
    code = data["code"]

    # имитируем «/start <код>» через poll_link_updates
    async def fake_updates(method, **params):
        if method == "getUpdates":
            return [
                {
                    "update_id": 10,
                    "message": {
                        "text": f"/start {code}",
                        "chat": {"id": 424242},
                    },
                }
            ]
        if method == "sendMessage":
            return {"ok": True}
        return {"username": "legal_test_bot"}

    monkeypatch.setattr(telegram_service, "_call", fake_updates)
    async with db_factory() as session:
        next_offset = await telegram_service.poll_link_updates(session)
    assert next_offset == 11

    channels = (
        await client.get("/api/notifications/channels", headers=admin_headers)
    ).json()
    assert channels["telegram_linked"] is True

    # отвязка
    resp = await client.delete(
        "/api/notifications/telegram/link", headers=admin_headers
    )
    assert resp.status_code == 200
    channels = (
        await client.get("/api/notifications/channels", headers=admin_headers)
    ).json()
    assert channels["telegram_linked"] is False


async def test_channels_endpoint_defaults(client, admin_headers, monkeypatch):
    # Локальный .env может содержать реальные SMTP/Telegram — тест
    # проверяет именно состояние «ничего не настроено»
    from app.services import email as email_service

    monkeypatch.setattr(email_service.settings, "SMTP_HOST", "")
    monkeypatch.setattr(telegram_service.settings, "TELEGRAM_BOT_TOKEN", "")
    channels = (
        await client.get("/api/notifications/channels", headers=admin_headers)
    ).json()
    assert channels == {
        "email_enabled": False,
        "telegram_enabled": False,
        "telegram_linked": False,
        "bot_username": None,
    }
