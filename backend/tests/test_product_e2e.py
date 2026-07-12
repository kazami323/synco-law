import hashlib

import pytest

from app.db.models import LegalArticle, LegalDocument
from app.utils import llm


async def _seed_legal_source(db_factory):
    async with db_factory() as session:
        document = LegalDocument(
            source="lex.uz",
            source_id="10872",
            language="ru",
            jurisdiction="Uzbekistan",
            doc_type="law",
            title="О договорно-правовой базе деятельности хозяйствующих субъектов",
            url="https://lex.uz/ru/docs/10872",
            status="active",
        )
        session.add(document)
        await session.flush()
        content = (
            "Статья 21. Правовая экспертиза хозяйственных договоров\n"
            "Хозяйственные договоры в процессе подготовки к заключению должны "
            "быть проверены юридической службой."
        )
        session.add(
            LegalArticle(
                document_id=document.id,
                source_article_id="11670",
                article_number="21",
                title="Статья 21. Правовая экспертиза хозяйственных договоров",
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                position=1,
                url="https://lex.uz/ru/docs/10872#11670",
            )
        )
        await session.commit()


@pytest.fixture
def product_llm(monkeypatch):
    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", "test-key")

    async def fake_llm_json(*, system: str, user: str, max_tokens: int = 4000) -> dict:
        if '"legal_issues"' in system:
            assert "lex.uz/ru/docs/10872#11670" in user
            return {
                "legal_issues": [
                    {
                        "issue": "Нужна правовая экспертиза договора",
                        "applicable_law": "О договорно-правовой базе деятельности хозяйствующих субъектов",
                        "article": "статья 21",
                        "source_url": "https://lex.uz/ru/docs/10872#11670",
                        "violation_type": "missing",
                        "recommendation": "Провести проверку юридической службой до подписания.",
                    }
                ],
                "compliance_status": "partial",
                "recommendations": ["Добавить отметку о правовой экспертизе."],
            }
        if '"errors"' in system:
            return {
                "errors": [],
                "missing_terms": [],
                "summary": "Структура договора достаточна для пилотной проверки.",
            }
        return {
            "overall_score": 35,
            "category": "low",
            "risk_factors": [],
            "mitigation": [],
            "recommendation": "Можно согласовывать после проверки источников.",
        }

    async def fake_llm_text(*, system: str, messages: list, max_tokens: int = 4000) -> str:
        assert "lex.uz/ru/docs/10872#11670" in system
        return (
            "По статье 21 закона о договорно-правовой базе договор должен пройти "
            "правовую экспертизу: https://lex.uz/ru/docs/10872#11670"
        )

    monkeypatch.setattr(llm, "llm_json", fake_llm_json)
    monkeypatch.setattr(llm, "llm_text", fake_llm_text)


async def test_full_product_flow(
    client,
    admin_headers,
    db_factory,
    product_llm,
):
    await _seed_legal_source(db_factory)

    finance = await client.post(
        "/api/users/",
        json={
            "email": "finance-e2e@test.uz",
            "username": "finance-e2e",
            "password": "Secret1234",
            "role": "finance",
        },
        headers=admin_headers,
    )
    assert finance.status_code == 201, finance.text
    finance_login = await client.post(
        "/api/auth/login",
        json={"email": "finance-e2e@test.uz", "password": "Secret1234"},
    )
    finance_headers = {
        "Authorization": f"Bearer {finance_login.json()['access_token']}"
    }

    upload = await client.post(
        "/api/contracts/upload",
        data={
            "title": "E2E договор поставки",
            "contract_type": "purchase",
            "counterparty": "ООО E2E",
            "amount": "1000000",
            "currency": "UZS",
        },
        files={
            "file": (
                "contract.txt",
                (
                    "ДОГОВОР ПОСТАВКИ\n"
                    "1. Предмет договора.\n"
                    "2. Срок оплаты 10 дней.\n"
                    "3. Ответственность за просрочку оплаты.\n"
                    "4. Требуется правовая экспертиза хозяйственного договора."
                ).encode("utf-8"),
                "text/plain",
            )
        },
        headers=admin_headers,
    )
    assert upload.status_code == 201, upload.text
    contract = upload.json()
    assert contract["file_path"]

    analysis = await client.post(
        f"/api/contracts/{contract['id']}/analyze", headers=admin_headers
    )
    assert analysis.status_code == 200, analysis.text
    law = analysis.json()["analysis"]["law_agent"]
    assert law["source"] == "local_lexuz_rag"
    assert law["legal_sources"][0]["url"] == "https://lex.uz/ru/docs/10872#11670"

    chat = await client.post(
        "/api/agents/chat",
        json={
            "agent": "law",
            "contract_id": contract["id"],
            "messages": [
                {
                    "role": "user",
                    "content": "Какая статья требует правовую экспертизу договора?",
                }
            ],
        },
        headers=admin_headers,
    )
    assert chat.status_code == 200, chat.text
    assert "lex.uz/ru/docs/10872#11670" in chat.json()["reply"]

    approve = await client.post(
        f"/api/contracts/{contract['id']}/workflow/approve_legal",
        json={"comment": "Юридически согласовано"},
        headers=admin_headers,
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "approved"

    finance_approve = await client.post(
        f"/api/contracts/{contract['id']}/workflow/approve_finance",
        json={"comment": "Финансы согласовали"},
        headers=finance_headers,
    )
    assert finance_approve.status_code == 200, finance_approve.text
    assert finance_approve.json()["status"] == "approved_finance"

    finalize = await client.post(
        f"/api/contracts/{contract['id']}/workflow/finalize",
        json={"comment": "Передано на подпись"},
        headers=admin_headers,
    )
    assert finalize.status_code == 200, finalize.text
    assert finalize.json()["status"] == "ready_to_sign"

    sign_request = await client.post(
        f"/api/contracts/{contract['id']}/sign-request",
        json={},
        headers=admin_headers,
    )
    assert sign_request.status_code == 200, sign_request.text
    request_data = sign_request.json()
    assert len(request_data["hash"]) == 64

    sign_confirm = await client.post(
        f"/api/contracts/{contract['id']}/sign-confirm",
        json={"request_id": request_data["request_id"], "pin": "123456"},
        headers=admin_headers,
    )
    assert sign_confirm.status_code == 200, sign_confirm.text
    assert sign_confirm.json()["signature"].startswith("EIMZO-STUB-SIGNATURE")

    archive = await client.delete(
        f"/api/contracts/{contract['id']}", headers=admin_headers
    )
    assert archive.status_code == 200, archive.text

    detail = await client.get(
        f"/api/contracts/{contract['id']}", headers=admin_headers
    )
    assert detail.status_code == 200
    assert detail.json()["status"] == "archived"
