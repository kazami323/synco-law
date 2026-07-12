"""Тесты AI-агентов: оркестратор, анализ, чат, генерация — LLM замокан."""

import uuid

import pytest

from app.agents.chat import AgentChatResult
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
    reply = resp.json()["reply"]
    assert "ГК РУз" in reply
    assert "Примечание юриста:" in reply
    assert (
        "Правовое основание:" in reply
        or "Прямое регулирование данного вопроса на Lex.uz не выявлено" in reply
    )


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


async def test_chat_restores_document_context_from_session(
    client, admin_headers, mock_llm, monkeypatch
):
    contexts: list[tuple[str | None, str | None]] = []

    async def capture_chat(
        agent: str,
        messages: list[dict],
        context_document: str | None = None,
        context_label: str | None = None,
        db=None,
    ) -> str:
        contexts.append((context_document, context_label))
        return AgentChatResult(
            reply="Контекст получен",
            legal_sources=[
                {
                    "document_title": "Гражданский кодекс",
                    "article_number": "10",
                    "url": "https://lex.uz/docs/test#10",
                    "current_revision_date": "2026-01-01",
                    "status": "active",
                }
            ],
        )

    monkeypatch.setattr("app.api.agents.agent_chat", capture_chat)
    session_id = str(uuid.uuid4())
    first = await client.post(
        "/api/agents/chat",
        json={
            "agent": "risk",
            "messages": [{"role": "user", "content": "Проанализируй документ"}],
            "document_text": "Существенное обязательство по оплате",
            "document_name": "agreement.pdf",
            "session_id": session_id,
        },
        headers=admin_headers,
    )
    assert first.status_code == 200
    assert first.json()["sources"][0]["article_number"] == "10"

    second = await client.post(
        "/api/agents/chat",
        json={
            "agent": "risk",
            "messages": [{"role": "user", "content": "А какой срок?"}],
            "session_id": session_id,
        },
        headers=admin_headers,
    )
    assert second.status_code == 200
    assert contexts == [
        ("Существенное обязательство по оплате", "agreement.pdf"),
        ("Существенное обязательство по оплате", "agreement.pdf"),
    ]

    sessions = await client.get("/api/agents/sessions/", headers=admin_headers)
    stored = next(item for item in sessions.json() if item["id"] == session_id)
    assert "document_text" not in stored

    feedback = await client.put(
        f"/api/agents/sessions/{session_id}/messages/1/feedback",
        json={"rating": "up"},
        headers=admin_headers,
    )
    assert feedback.status_code == 204
    sessions = await client.get("/api/agents/sessions/", headers=admin_headers)
    stored = next(item for item in sessions.json() if item["id"] == session_id)
    assert stored["messages"][1]["feedback"] == "up"


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
    assert resp.json()["status"] == "done"
    assert resp.json()["text"] == "Текст документа для чата"


async def test_parse_scanned_pdf_via_background_job(
    client, admin_headers, mock_llm, monkeypatch
):
    """Скан без текстового слоя уходит в фоновый OCR: job_id + поллинг."""
    import asyncio

    from pypdf import PdfWriter

    from app.api import agents as agents_api

    async def fake_ocr(data: bytes, filename: str) -> str:
        return "Распознанный текст скана"

    monkeypatch.setattr(agents_api, "extract_pdf_text", fake_ocr)

    import io

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)

    resp = await client.post(
        "/api/agents/parse-file",
        files={"file": ("scan.pdf", buf.getvalue(), "application/pdf")},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "processing"
    job_id = body["job_id"]

    # Дать фоновой задаче исполниться (включая запись usage в БД)
    for _ in range(100):
        await asyncio.sleep(0.1)
        status = await client.get(
            f"/api/agents/parse-file/jobs/{job_id}", headers=admin_headers
        )
        assert status.status_code == 200
        if status.json()["status"] == "done":
            break
    assert status.json()["status"] == "done"
    assert status.json()["text"] == "Распознанный текст скана"
    assert status.json()["extraction_method"] == "ocr"


def test_pdf_chunks_split_and_limits():
    """Нарезка PDF для OCR: по 10 страниц, с потолком в 150 страниц."""
    import io

    import pytest
    from pypdf import PdfWriter

    from app.utils.llm import OCR_MAX_PAGES, _pdf_chunks

    def make_pdf(pages: int) -> bytes:
        writer = PdfWriter()
        for _ in range(pages):
            writer.add_blank_page(width=200, height=200)
        buffer = io.BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    chunks = _pdf_chunks(make_pdf(25))
    assert [label for label, _ in chunks] == ["стр. 1-10", "стр. 11-20", "стр. 21-25"]

    with pytest.raises(ValueError, match="Разбейте файл"):
        _pdf_chunks(make_pdf(OCR_MAX_PAGES + 1))


async def test_parse_job_of_other_user_is_hidden(client, admin_headers, mock_llm, monkeypatch):
    """Чужую задачу распознавания нельзя прочитать по job_id."""
    import io

    from pypdf import PdfWriter

    from app.api import agents as agents_api
    from tests.conftest import register_and_login

    async def slow_ocr(data: bytes, filename: str) -> str:
        return "x"

    monkeypatch.setattr(agents_api, "extract_pdf_text", slow_ocr)

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    resp = await client.post(
        "/api/agents/parse-file",
        files={"file": ("scan.pdf", buf.getvalue(), "application/pdf")},
        headers=admin_headers,
    )
    job_id = resp.json()["job_id"]

    other_headers = await register_and_login(
        client, email="other@test.uz", username="other"
    )
    other = await client.get(
        f"/api/agents/parse-file/jobs/{job_id}", headers=other_headers
    )
    assert other.status_code == 404


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
