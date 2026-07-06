"""Тесты AI-агентов: оркестратор, анализ, чат, генерация — LLM замокан."""

import pytest

from app.utils import llm

FAKE_ANALYZER = {
    "errors": [
        {
            "severity": "critical",
            "location": "п. 3",
            "description": "Не указан срок оплаты",
            "recommendation": "Добавить срок оплаты",
        }
    ],
    "missing_terms": ["срок оплаты"],
    "summary": "Структура в целом корректна",
}
FAKE_LAW = {
    "legal_issues": [
        {
            "issue": "Нет порядка разрешения споров",
            "applicable_law": "ГК РУз",
            "article": "ст. 354",
            "violation_type": "missing",
            "recommendation": "Добавить раздел о спорах",
        }
    ],
    "compliance_status": "partial",
    "recommendations": ["Добавить раздел о спорах"],
}
FAKE_RISK = {
    "overall_score": 55,
    "category": "medium",
    "risk_factors": [
        {"factor": "Неопределённый срок оплаты", "severity": 6, "impact": "financial"}
    ],
    "mitigation": ["Зафиксировать сроки оплаты"],
    "recommendation": "Доработать",
}


@pytest.fixture
def mock_llm(monkeypatch):
    """Подменяет вызовы модели: llm_json отвечает по содержимому system-промпта."""
    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", "test-key")

    async def fake_llm_json(*, system: str, user: str, max_tokens: int = 4000) -> dict:
        if "юрист-аналитик" in system:
            return FAKE_ANALYZER
        if "законодательству Республики Узбекистан" in system:
            return FAKE_LAW
        return FAKE_RISK

    async def fake_llm_text(*, system: str, messages: list, max_tokens: int = 4000) -> str:
        if "составляющий договоры" in system:
            return "ДОГОВОР ПОСТАВКИ №1\n1. СТОРОНЫ..."
        return "Ответ агента: по ст. 354 ГК РУз рекомендую добавить раздел о спорах."

    monkeypatch.setattr(llm, "llm_json", fake_llm_json)
    monkeypatch.setattr(llm, "llm_text", fake_llm_text)


async def _make_contract(client, headers) -> str:
    resp = await client.post(
        "/api/contracts/",
        json={
            "title": "Договор для анализа",
            "contract_type": "purchase",
            "content": "ДОГОВОР ПОСТАВКИ\n1. СТОРОНЫ...",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_analyze_endpoint_saves_results(client, admin_headers, mock_llm):
    cid = await _make_contract(client, admin_headers)

    resp = await client.post(f"/api/contracts/{cid}/analyze", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert report["overall_assessment"]["risk_score"] == 55
    assert report["overall_assessment"]["legal_compliance"] == "partial"
    assert report["overall_assessment"]["recommendation"] == "Требуется доработка"

    # risk_score и статус обновились на контракте
    detail = (
        await client.get(f"/api/contracts/{cid}", headers=admin_headers)
    ).json()
    assert detail["risk_score"] == 55
    assert detail["status"] == "analyzed"

    # результаты сохранены и читаются
    saved = (
        await client.get(f"/api/contracts/{cid}/analysis", headers=admin_headers)
    ).json()
    assert set(saved["analysis"].keys()) == {
        "contract_analyzer",
        "law_agent",
        "risk_agent",
    }
    assert saved["analysis"]["risk_agent"]["category"] == "medium"


async def test_analyze_requires_content(client, admin_headers, mock_llm):
    resp = await client.post(
        "/api/contracts/",
        json={"title": "Пустой", "contract_type": "other"},
        headers=admin_headers,
    )
    cid = resp.json()["id"]
    resp = await client.post(f"/api/contracts/{cid}/analyze", headers=admin_headers)
    assert resp.status_code == 400


async def test_analyze_without_api_key_returns_503(client, admin_headers, monkeypatch):
    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", "")
    cid = await _make_contract(client, admin_headers)
    resp = await client.post(f"/api/contracts/{cid}/analyze", headers=admin_headers)
    assert resp.status_code == 503


async def test_chat_with_agent(client, admin_headers, mock_llm):
    resp = await client.post(
        "/api/agents/chat",
        json={
            "agent": "law",
            "messages": [
                {"role": "user", "content": "Какие требования к NDA в РУз?"}
            ],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert "ГК РУз" in resp.json()["reply"]


async def test_chat_with_contract_context(client, admin_headers, mock_llm):
    cid = await _make_contract(client, admin_headers)
    resp = await client.post(
        "/api/agents/chat",
        json={
            "agent": "analyzer",
            "messages": [{"role": "user", "content": "Что не так с договором?"}],
            "contract_id": cid,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200


async def test_chat_unknown_agent(client, admin_headers, mock_llm):
    resp = await client.post(
        "/api/agents/chat",
        json={
            "agent": "hacker",
            "messages": [{"role": "user", "content": "hi"}],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_draft_generation(client, admin_headers, mock_llm):
    resp = await client.post(
        "/api/agents/draft",
        json={
            "contract_type": "purchase",
            "requirements": {"поставщик": "ООО ABC", "сумма": "100 млн UZS"},
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert "ДОГОВОР" in resp.json()["content"]


async def test_parse_file_for_chat(client, admin_headers):
    resp = await client.post(
        "/api/agents/parse-file",
        files={"file": ("note.txt", "Текст документа для чата".encode(), "text/plain")},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["text"] == "Текст документа для чата"


# ---------- Phase 2: Translation Agent и Compliance Agent ----------

FAKE_COMPLIANCE = {
    "violations": [
        {
            "policy": "Лимит предоплаты 30%",
            "description": "В договоре предоплата 100%",
            "severity": "critical",
            "recommendation": "Снизить предоплату до 30%",
        }
    ],
    "compliance_score": 40,
    "status": "non-compliant",
    "summary": "Нарушен лимит предоплаты",
}


@pytest.fixture
def mock_llm_phase2(monkeypatch):
    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", "test-key")

    async def fake_llm_json(*, system: str, user: str, max_tokens: int = 4000) -> dict:
        if "комплаенс-офицер" in system:
            return FAKE_COMPLIANCE
        if "юрист-аналитик" in system:
            return FAKE_ANALYZER
        if "законодательству Республики Узбекистан" in system:
            return FAKE_LAW
        return FAKE_RISK

    async def fake_llm_text(*, system: str, messages: list, max_tokens: int = 4000) -> str:
        if "переводчик" in system:
            return "SHARTNOMA №1 (перевод на узбекский)"
        return "Ответ агента"

    monkeypatch.setattr(llm, "llm_json", fake_llm_json)
    monkeypatch.setattr(llm, "llm_text", fake_llm_text)


async def test_translate_contract(client, admin_headers, mock_llm_phase2):
    cid = await _make_contract(client, admin_headers)
    resp = await client.post(
        f"/api/contracts/{cid}/translate",
        json={"target_lang": "uz"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert "SHARTNOMA" in resp.json()["content"]

    # перевод не подмешивается в результаты анализа
    saved = (
        await client.get(f"/api/contracts/{cid}/analysis", headers=admin_headers)
    ).json()
    assert "translation_agent" not in saved["analysis"]


async def test_translate_unsupported_language(client, admin_headers, mock_llm_phase2):
    cid = await _make_contract(client, admin_headers)
    resp = await client.post(
        f"/api/contracts/{cid}/translate",
        json={"target_lang": "fr"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_analysis_includes_compliance_when_policies_set(
    client, admin_headers, mock_llm_phase2
):
    resp = await client.put(
        "/api/organizations/me",
        json={"compliance_policies": "Предоплата не более 30%. Запрещены бессрочные договоры."},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert "30%" in resp.json()["compliance_policies"]

    cid = await _make_contract(client, admin_headers)
    report = (
        await client.post(f"/api/contracts/{cid}/analyze", headers=admin_headers)
    ).json()
    assert report["analysis"]["compliance_agent"]["status"] == "non-compliant"
    assert report["overall_assessment"]["policy_compliance"] == "non-compliant"
    assert report["overall_assessment"]["recommendation"] == "Требуется доработка"
    assert any("политикам" in step for step in report["next_steps"])

    saved = (
        await client.get(f"/api/contracts/{cid}/analysis", headers=admin_headers)
    ).json()
    assert "compliance_agent" in saved["analysis"]


async def test_analysis_skips_compliance_without_policies(
    client, admin_headers, mock_llm_phase2
):
    cid = await _make_contract(client, admin_headers)
    report = (
        await client.post(f"/api/contracts/{cid}/analyze", headers=admin_headers)
    ).json()
    assert "compliance_agent" not in report["analysis"]


async def test_chat_with_new_agents(client, admin_headers, mock_llm_phase2):
    for agent in ("translator", "compliance"):
        resp = await client.post(
            "/api/agents/chat",
            json={"agent": agent, "messages": [{"role": "user", "content": "тест"}]},
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text
