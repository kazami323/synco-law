"""Тесты сохранения AI-проверки отдельным документом проекта."""

import uuid

from app.db.models import AgentResult
from app.services.review_document import render_review

ANALYSIS = {
    "risk_agent": {
        "overall_score": 72,
        "category": "high",
        "recommendation": "Требуется доработка",
        "risk_factors": [
            {"factor": "Безграничная ответственность", "severity": 9, "impact": "Убытки"}
        ],
    },
    "contract_analyzer": {
        "summary": "Структура в целом соответствует",
        "errors": [
            {
                "severity": "warning",
                "location": "п.5",
                "description": "Не указан срок оплаты",
                "recommendation": "Добавить срок",
            }
        ],
        "missing_terms": ["Форс-мажор"],
    },
    "law_agent": {
        "compliance_status": "partial",
        "legal_issues": [
            {
                "issue": "Применяется иностранное право",
                "applicable_law": "ГК РУз",
                "article": "ст. 1189",
                "recommendation": "Указать право РУз",
            }
        ],
    },
}

CONTRACT = {
    "title": "Договор поставки №7",
    "contract_type": "service",
    "content": "1. ПРЕДМЕТ...",
}


async def _create(client, headers, **overrides):
    resp = await client.post(
        "/api/contracts/", json={**CONTRACT, **overrides}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_render_review_contains_all_sections():
    text = render_review("Договор поставки №7", ANALYSIS)
    assert "ПРОВЕРКА КОНТРАКТА" in text
    assert "Договор поставки №7" in text
    assert "72/100" in text
    assert "Безграничная ответственность" in text
    assert "Не указан срок оплаты" in text
    assert "Форс-мажор" in text
    assert "ГК РУз" in text
    assert "ст. 1189" in text


def test_render_review_survives_empty_analysis():
    # Пустой анализ не должен ронять рендер
    text = render_review("Пустой", {})
    assert "ПРОВЕРКА КОНТРАКТА" in text
    assert "Пустой" in text


async def test_save_review_creates_project_document(client, admin_headers, db_factory):
    project = (
        await client.post(
            "/api/projects/", json={"name": "Клиент А"}, headers=admin_headers
        )
    ).json()
    contract = await _create(
        client, admin_headers, title="Договор поставки", project_id=project["id"]
    )

    # Живой AI в тестах недоступен — засеваем результат анализа напрямую в БД.
    async with db_factory() as db:
        db.add_all(
            [
                AgentResult(
                    contract_id=uuid.UUID(contract["id"]),
                    agent_name=name,
                    result_type="analysis",
                    result_data=data,
                )
                for name, data in ANALYSIS.items()
            ]
        )
        await db.commit()

    resp = await client.post(
        f"/api/contracts/{contract['id']}/save-review", headers=admin_headers
    )
    assert resp.status_code == 201, resp.text
    review = resp.json()

    assert review["contract_type"] == "contract_review"
    assert review["project_id"] == project["id"]
    assert review["title"] == "Проверка: Договор поставки"
    # Документ — продукт ИИ: на нём сразу плашка «Проверено ИИ»
    assert [label["kind"] for label in review["labels"]] == ["ai_reviewed"]

    detail = (
        await client.get(
            f"/api/contracts/{review['id']}", headers=admin_headers
        )
    ).json()
    assert "ПРОВЕРКА КОНТРАКТА" in detail["content"]
    assert "72/100" in detail["content"]
    assert "ГК РУз" in detail["content"]

    # Исходный договор + проверка — оба в одном проекте
    listing = (
        await client.get(
            f"/api/contracts/?project_id={project['id']}&limit=10",
            headers=admin_headers,
        )
    ).json()
    assert listing["total"] == 2


async def test_save_review_requires_analysis(client, admin_headers):
    contract = await _create(client, admin_headers)
    resp = await client.post(
        f"/api/contracts/{contract['id']}/save-review", headers=admin_headers
    )
    assert resp.status_code == 400
    assert "анализ" in resp.json()["detail"].lower()
