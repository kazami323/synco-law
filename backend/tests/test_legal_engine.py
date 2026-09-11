"""Тесты правового движка: разбивка на пункты, Модули 1-3, шаблоны, экспорт.

Покрывают правила ТЗ, нарушение которых вредит юристу: блокировку статуса до
подтверждения всех пунктов, запрет редактирования в «Финальном», отказ от
вердикта «противоречит» без подтверждённой нормы и изоляцию организаций.
"""

import pytest

from app.agents.clause_checker import normalize_verdicts, source_snapshot
from app.agents.logic_agent import normalize_findings
from app.agents.risk_agent import normalize_risk_result
from app.services import clause_splitter
from app.services.logic_check import detect_broken_references
from app.utils import llm
from tests.conftest import register_and_login

CONTRACT_TEXT = """ДОГОВОР ПОСТАВКИ № 17

ООО «Альфа», именуемое в дальнейшем «Поставщик», и ИП Петров,
именуемый в дальнейшем «Покупатель», заключили настоящий Договор.

1. ПРЕДМЕТ ДОГОВОРА
1.1. Поставщик обязуется поставить оборудование в соответствии с п. 3.1.
1.2. Наименование и количество товара указаны в Спецификации.

2. ЦЕНА И ПОРЯДОК РАСЧЁТОВ
2.1. Общая стоимость товара составляет 500 000 000 сум.
2.2. Покупатель вносит предоплату 30 процентов.

3. СРОКИ ПОСТАВКИ
3.1. Поставка осуществляется в течение 30 дней.
3.2. Стороны действуют в порядке, установленном в п. 9.7 Договора.
"""


# --------------------------------------------------------------------------
# Разбивка на пункты (чистые функции)
# --------------------------------------------------------------------------


def test_splitter_builds_numbered_tree():
    clauses = clause_splitter.split_document(CONTRACT_TEXT)
    anchors = [clause.anchor for clause in clauses]

    assert "1.1" in anchors and "2.2" in anchors and "3.2" in anchors
    by_anchor = {clause.anchor: clause for clause in clauses}
    assert by_anchor["1.1"].parent_anchor == "1"
    assert by_anchor["1"].title == "ПРЕДМЕТ ДОГОВОРА"
    assert by_anchor["1"].level == 1
    assert by_anchor["1.1"].level == 2


def test_splitter_does_not_treat_leading_number_as_clause():
    """«12 месяцев с даты» в начале строки — это условие, а не пункт 12."""
    text = "1. СРОКИ\n1.1. Договор действует\n12 месяцев с даты подписания.\n1.2. Далее."
    clauses = clause_splitter.split_document(text)
    anchors = [clause.anchor for clause in clauses]

    assert "12" not in anchors
    body = next(c for c in clauses if c.anchor == "1.1").content
    assert "12 месяцев" in body


def test_splitter_handles_letter_subclauses():
    text = (
        "1. ОБЯЗАННОСТИ\n"
        "1.1. Покупатель обязан:\n"
        "а) принять товар;\n"
        "б) оплатить товар.\n"
    )
    clauses = clause_splitter.split_document(text)
    anchors = [clause.anchor for clause in clauses]

    assert "1.1.а" in anchors and "1.1.б" in anchors
    assert next(c for c in clauses if c.anchor == "1.1.а").parent_anchor == "1.1"


def test_splitter_falls_back_to_paragraphs_without_numbering():
    text = "Первый абзац договора.\n\nВторой абзац договора.\n\nТретий абзац."
    clauses = clause_splitter.split_document(text)

    assert len(clauses) == 3
    assert all(clause.anchor.startswith("§") for clause in clauses)


def test_splitter_ignores_ocr_page_numbers():
    text = "1. РАЗДЕЛ\n1.1. Условие договора.\n12\n1.2. Второе условие."
    clauses = clause_splitter.split_document(text)

    assert "12" not in next(c for c in clauses if c.anchor == "1.1").content


def test_content_hash_ignores_whitespace():
    assert clause_splitter.content_hash("Оплата  в течение\n30 дней") == (
        clause_splitter.content_hash("оплата в течение 30 дней")
    )


def test_find_references_extracts_clause_numbers():
    refs = clause_splitter.find_references(
        "в соответствии с п. 3.2 и пунктом 5 настоящего Договора"
    )
    assert "3.2" in refs and "5" in refs


# --------------------------------------------------------------------------
# Модуль 2: детерминированные проверки
# --------------------------------------------------------------------------


class _FakeClause:
    def __init__(self, anchor, content, number=None, title=None):
        self.anchor = anchor
        self.content = content
        self.number = number or anchor
        self.title = title
        self.id = anchor
        self.parent_id = None


def test_broken_reference_detected():
    clauses = [
        _FakeClause("1.1", "Поставка в порядке, указанном в п. 9.7 Договора."),
        _FakeClause("1.2", "Оплата производится по п. 1.1."),
    ]
    findings = detect_broken_references(clauses)

    assert len(findings) == 1
    assert findings[0]["category"] == "broken_refs"
    assert "9.7" in findings[0]["description"]
    assert findings[0]["clause_anchors"] == ["1.1"]


def test_reference_to_existing_section_is_not_broken():
    clauses = [
        _FakeClause("3", "СРОКИ", title="СРОКИ"),
        _FakeClause("3.1", "Порядок описан в разделе 3."),
    ]
    assert detect_broken_references(clauses) == []


# --------------------------------------------------------------------------
# Защита от выдуманных норм и негодных находок
# --------------------------------------------------------------------------


def test_conflict_verdict_downgraded_without_verified_source():
    """«Противоречит» без подтверждённой статьи юристу не показываем."""
    clauses = [{"anchor": "2.1", "content": "Оплата в разумный срок"}]
    raw = {
        "verdicts": [
            {
                "anchor": "2.1",
                "verdict": "conflicts",
                "rationale": "Нарушает статью 999",
                "source_ids": ["L7"],  # такого источника не передавали
            }
        ]
    }
    result = normalize_verdicts(raw, clauses, sources=[])

    assert result[0]["verdict"] == "attention"
    assert result[0]["sources"] == []
    assert "не подтверждена" in result[0]["rationale"]


def test_verdict_source_is_taken_from_passed_norms_only():
    clauses = [{"anchor": "2.1", "content": "Оплата"}]
    sources = [
        {
            "document_title": "Гражданский кодекс РУз",
            "article_number": "354",
            "content": "текст статьи",
            "url": "https://lex.uz/docs/1#354",
            "current_revision_date": "2025-01-01",
        }
    ]
    raw = {
        "verdicts": [
            {
                "anchor": "2.1",
                "verdict": "conflicts",
                "rationale": "Противоречит",
                "source_ids": ["L1"],
                "suggested_text": "Оплата в течение 30 календарных дней.",
            }
        ]
    }
    result = normalize_verdicts(raw, clauses, sources)

    assert result[0]["verdict"] == "conflicts"
    assert result[0]["sources"][0]["article_number"] == "354"
    # Редакция нормы обязана уехать в снапшот: без неё результат
    # невоспроизводим после обновления законодательства.
    assert result[0]["sources"][0]["current_revision_date"] == "2025-01-01"
    assert result[0]["suggested_text"]


def test_unknown_verdict_becomes_no_norm():
    clauses = [{"anchor": "1.1", "content": "Текст"}]
    raw = {"verdicts": [{"anchor": "1.1", "verdict": "возможно нарушение"}]}
    assert normalize_verdicts(raw, clauses, [])[0]["verdict"] == "no_norm"


def test_source_snapshot_preserves_repealed_reference_status():
    """D3: снапшот нормы обязан нести признак отмены, иначе в карточке пункта
    отменённая статья выглядит действующей нормой (clause_checker.py:165 —
    source_snapshot копирует восемь полей и теряет reference_status,
    repealed_at, historical_revision_date, repeal_notice, repeal_law_url,
    хотя legal_search.py их собирает при поиске по точной ссылке на
    историческую редакцию, см. _search_exact_reference)."""
    source = {
        "document_title": "Гражданский кодекс Республики Узбекистан (часть первая)",
        "document_number": None,
        "article_number": "66",
        "article_title": "Статья 66. Закрытое акционерное общество",
        "content": "Статья 66. Закрытое акционерное общество. Утратила силу.",
        "url": "https://lex.uz/ru/docs/111181?ONDATE=01.03.1997%2000#156804",
        "current_revision_date": None,
        "status": "active",
        "reference_status": "repealed",
        "repealed_at": "2014-05-15",
        "historical_revision_date": "1997-03-01",
        "repeal_notice": (
            "Статьи 65 и 66 утратили силу в соответствии с Законом "
            "Республики Узбекистан от 14 мая 2014 года № ЗРУ-372."
        ),
        "repeal_law_url": "https://lex.uz/ru/docs/2388209",
    }

    snapshot = source_snapshot(source)

    assert snapshot["reference_status"] == "repealed"
    assert snapshot["repealed_at"] == "2014-05-15"
    assert snapshot["historical_revision_date"] == "1997-03-01"
    assert snapshot["repeal_notice"] == source["repeal_notice"]
    assert snapshot["repeal_law_url"] == "https://lex.uz/ru/docs/2388209"


def test_verdict_sources_preserve_repealed_status_end_to_end():
    """Тот же дефект D3, но на границе, которую видит остальная система:
    источник вердикта по пункту (result["sources"]) обязан донести признак
    отмены нормы до вызывающего кода, а не только сам source_snapshot()."""
    clauses = [{"anchor": "3.2", "content": "Общество создаётся в форме ЗАО"}]
    sources = [
        {
            "document_title": "Гражданский кодекс Республики Узбекистан (часть первая)",
            "article_number": "66",
            "content": "Статья 66. Закрытое акционерное общество. Утратила силу.",
            "url": "https://lex.uz/ru/docs/111181#156804",
            "current_revision_date": None,
            "reference_status": "repealed",
            "repealed_at": "2014-05-15",
            "historical_revision_date": "1997-03-01",
            "repeal_notice": "Утратила силу Законом № ЗРУ-372 от 14.05.2014.",
            "repeal_law_url": "https://lex.uz/ru/docs/2388209",
        }
    ]
    raw = {
        "verdicts": [
            {
                "anchor": "3.2",
                "verdict": "compliant",
                "rationale": "Соответствует ст. 66 ГК",
                "source_ids": ["L1"],
            }
        ]
    }

    result = normalize_verdicts(raw, clauses, sources)

    assert result[0]["sources"][0]["reference_status"] == "repealed"
    assert result[0]["sources"][0]["repeal_notice"] == (
        "Утратила силу Законом № ЗРУ-372 от 14.05.2014."
    )


def test_logic_finding_without_pair_is_dropped():
    """ТЗ обещает показать оба конфликтующих пункта рядом."""
    raw = {
        "findings": [
            {
                "category": "deadlines",
                "description": "Где-то расходятся сроки",
                "clause_anchors": ["2.1"],
            },
            {
                "category": "deadlines",
                "description": "п. 2.1 — 30 дней, п. 3.1 — 45 дней",
                "clause_anchors": ["2.1", "3.1"],
            },
        ]
    }
    findings = normalize_findings(raw, {"2.1", "3.1"})

    assert len(findings) == 1
    assert findings[0]["clause_anchors"] == ["2.1", "3.1"]


def test_logic_finding_with_invented_anchor_is_dropped():
    raw = {
        "findings": [
            {
                "category": "amounts",
                "description": "Суммы расходятся",
                "clause_anchors": ["2.1", "99.9"],
            }
        ]
    }
    assert normalize_findings(raw, {"2.1", "3.1"}) == []


def test_risk_result_keeps_only_known_categories_and_levels():
    raw = {
        "risks": [
            {
                "category": "asymmetry",
                "level": "критический",
                "description": "Штрафы только для нас",
                "consequence": "Взыскать с контрагента нечего",
                "mitigation": "Добавить симметричную неустойку",
                "clause_anchors": ["4.1", "нет такого"],
            },
            {"category": "выдуманная", "level": "high", "description": "..."},
        ],
        "overall_score": 71,
    }
    result = normalize_risk_result(raw, {"4.1"})

    assert len(result["risks"]) == 1
    assert result["risks"][0]["level"] == "medium"  # неизвестный уровень
    assert result["risks"][0]["clause_anchors"] == ["4.1"]
    assert result["overall_level"] == "high"


# --------------------------------------------------------------------------
# HTTP: пункты, решения юриста, статусы
# --------------------------------------------------------------------------


@pytest.fixture
def mock_llm(monkeypatch):
    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", "test-key")

    async def fake_llm_json(*, system: str, user: str, max_tokens: int = 4000) -> dict:
        if "ОТДЕЛЬНЫЕ ПУНКТЫ" in system:
            return {"verdicts": []}
        if "внутреннюю непротиворечивость" in system or "вычитывающий договор" in system:
            return {"findings": []}
        if "защищает интересы" in system:
            return {"risks": [], "overall_score": 10, "summary": "Ок"}
        return {}

    async def fake_llm_text(*, system: str, messages: list, max_tokens: int = 4000) -> str:
        return "1. РАЗДЕЛ\n1.1. Условие."

    monkeypatch.setattr(llm, "llm_json", fake_llm_json)
    monkeypatch.setattr(llm, "llm_text", fake_llm_text)


async def _make_contract(client, headers, content=CONTRACT_TEXT, title="Договор"):
    resp = await client.post(
        "/api/contracts/",
        json={"title": title, "contract_type": "supply", "content": content},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _make_user(client, admin_headers, email, username, role):
    resp = await client.post(
        "/api/users/",
        json={
            "email": email,
            "username": username,
            "password": "Secret1234",
            "role": role,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": "Secret1234"}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _confirm_all(client, headers, cid):
    clauses = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=headers)
    ).json()["items"]
    for clause in clauses:
        resp = await client.post(
            f"/api/clauses/{clause['id']}/decision",
            json={"action": "confirm"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
    return clauses


async def test_clauses_endpoint_builds_tree(client, admin_headers):
    cid = await _make_contract(client, admin_headers)

    resp = await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    anchors = [item["anchor"] for item in payload["items"]]
    assert "1.1" in anchors and "2.1" in anchors
    assert payload["progress"]["total"] == len(payload["items"])
    assert payload["progress"]["resolved"] == 0
    assert payload["locked"] is False


async def test_clause_decision_updates_progress_and_audit(client, admin_headers):
    cid = await _make_contract(client, admin_headers)
    items = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]
    target = next(item for item in items if item["anchor"] == "1.1")

    resp = await client.post(
        f"/api/clauses/{target['id']}/decision",
        json={"action": "confirm", "comment": "Норм"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    decision = resp.json()
    assert decision["action"] == "confirm"
    assert decision["decided_by_name"]  # решение подписано автором
    assert decision["created_at"]

    payload = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()
    assert payload["progress"]["confirmed"] == 1
    assert payload["progress"]["resolved"] == 1


async def test_clause_edit_rewrites_contract_text(client, admin_headers):
    cid = await _make_contract(client, admin_headers)
    items = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]
    target = next(item for item in items if item["anchor"] == "2.1")

    resp = await client.post(
        f"/api/clauses/{target['id']}/decision",
        json={"action": "edit", "new_text": "Стоимость составляет 400 000 000 сум."},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    detail = (await client.get(f"/api/contracts/{cid}", headers=admin_headers)).json()
    assert "400 000 000" in detail["content"]

    # ТЗ, раздел 5: каждая правка создаёт версию.
    versions = (
        await client.get(f"/api/contracts/{cid}/versions", headers=admin_headers)
    ).json()
    assert len(versions) == 2
    assert "2.1" in versions[0]["changes_description"]


async def test_clause_history_returns_previous_text(client, admin_headers):
    """R9: история пункта обязана нести прежнюю редакцию текста.

    Без неё нельзя показать юристу, что именно изменилось («0,5% → 0,1%»):
    колонка previous_text заполняется при правке, но наружу не отдавалась.
    """
    cid = await _make_contract(client, admin_headers)
    items = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]
    target = next(item for item in items if item["anchor"] == "2.1")
    original = target["content"]
    updated = "Стоимость составляет 400 000 000 сум."

    decision = await client.post(
        f"/api/clauses/{target['id']}/decision",
        json={"action": "edit", "new_text": updated},
        headers=admin_headers,
    )
    assert decision.status_code == 200, decision.text

    # Правка пересобирает дерево пунктов: у пункта новый идентификатор, а
    # решения переезжают на него по якорю. Прежний id после этого отдаёт 404.
    refreshed = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]
    moved = next(item for item in refreshed if item["anchor"] == "2.1")

    response = await client.get(
        f"/api/clauses/{moved['id']}/history", headers=admin_headers
    )
    assert response.status_code == 200, response.text
    edit = next(row for row in response.json() if row["action"] == "edit")

    assert edit["previous_text"] == original
    assert edit["new_text"] == updated


async def test_edit_decision_requires_new_text(client, admin_headers):
    cid = await _make_contract(client, admin_headers)
    items = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]

    resp = await client.post(
        f"/api/clauses/{items[0]['id']}/decision",
        json={"action": "edit"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_approve_blocked_until_all_clauses_confirmed(client, admin_headers):
    """Ключевое правило ТЗ: без прохода по всем пунктам статус не меняется."""
    cid = await _make_contract(client, admin_headers)
    items = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]

    await client.post(
        f"/api/clauses/{items[0]['id']}/decision",
        json={"action": "confirm"},
        headers=admin_headers,
    )
    resp = await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=admin_headers
    )
    assert resp.status_code == 409
    assert "не все пункты" in resp.json()["detail"]

    await _confirm_all(client, admin_headers, cid)
    resp = await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"


async def test_deferred_clause_does_not_count_as_resolved(client, admin_headers):
    cid = await _make_contract(client, admin_headers)
    items = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]
    for item in items:
        action = "defer" if item["anchor"] == "1.1" else "confirm"
        await client.post(
            f"/api/clauses/{item['id']}/decision",
            json={"action": action},
            headers=admin_headers,
        )

    payload = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()
    assert payload["progress"]["deferred"] == 1
    assert payload["progress"]["complete"] is False

    resp = await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=admin_headers
    )
    assert resp.status_code == 409


async def test_confirmation_becomes_stale_after_text_change(client, admin_headers):
    cid = await _make_contract(client, admin_headers)
    await _confirm_all(client, admin_headers, cid)

    changed = CONTRACT_TEXT.replace("30 дней", "45 дней")
    resp = await client.put(
        f"/api/contracts/{cid}",
        json={"content": changed},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    payload = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()
    # Пункт 3.1 переписали — подтверждение по нему больше не действует.
    assert payload["progress"]["stale"] >= 1
    assert payload["progress"]["complete"] is False


async def test_final_status_blocks_editing(client, admin_headers):
    """ТЗ, раздел 2: в «Финальном» редактирование заблокировано."""
    cid = await _make_contract(client, admin_headers)
    await _confirm_all(client, admin_headers, cid)
    for action in ("approve_legal", "approve_finance", "finalize"):
        resp = await client.post(
            f"/api/contracts/{cid}/workflow/{action}", json={}, headers=admin_headers
        )
        assert resp.status_code == 200, resp.text

    detail = (await client.get(f"/api/contracts/{cid}", headers=admin_headers)).json()
    assert detail["status"] == "ready_to_sign"

    resp = await client.put(
        f"/api/contracts/{cid}", json={"content": "Новый текст"}, headers=admin_headers
    )
    assert resp.status_code == 409
    assert "заблокировано" in resp.json()["detail"]


async def test_reject_returns_document_to_revision(client, admin_headers):
    cid = await _make_contract(client, admin_headers)
    await _confirm_all(client, admin_headers, cid)
    await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=admin_headers
    )

    resp = await client.post(
        f"/api/contracts/{cid}/workflow/reject",
        json={"comment": "Поправить неустойку"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "needs_revision"

    # Из «На доработке» документ снова можно подтвердить.
    resp = await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=admin_headers
    )
    assert resp.status_code == 200


async def test_finalize_is_closed_to_ordinary_lawyer(client, admin_headers):
    """ТЗ (раздел 7) отдаёт «Финальный» строке «Старший юрист / руководитель»,
    то есть обоим, но не рядовому юристу."""
    lawyer = await _make_user(
        client, admin_headers, "jun@test.uz", "junior", "lawyer"
    )
    senior = await _make_user(
        client, admin_headers, "senior@test.uz", "senior", "senior_lawyer"
    )
    cid = await _make_contract(client, admin_headers)
    await _confirm_all(client, admin_headers, cid)
    await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=admin_headers
    )
    await client.post(
        f"/api/contracts/{cid}/workflow/approve_finance", json={}, headers=admin_headers
    )

    denied = await client.post(
        f"/api/contracts/{cid}/workflow/finalize", json={}, headers=lawyer
    )
    assert denied.status_code == 403

    allowed = await client.post(
        f"/api/contracts/{cid}/workflow/finalize", json={}, headers=senior
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["status"] == "ready_to_sign"


async def test_lawyer_can_approve_and_archive(client, admin_headers):
    """ТЗ, раздел 2: автор статусов «Подтверждён юристом» и «В архиве» — юрист.
    Раньше у роли `lawyer` не было ни `approve`, ни права на архивацию:
    собственный документ юрист довести до конца не мог."""
    lawyer = await _make_user(
        client, admin_headers, "own@test.uz", "own-lawyer", "lawyer"
    )
    cid = await _make_contract(client, lawyer, title="Документ юриста")
    await _confirm_all(client, lawyer, cid)

    approved = await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=lawyer
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    archived = await client.delete(f"/api/contracts/{cid}", headers=lawyer)
    assert archived.status_code == 200, archived.text
    detail = (await client.get(f"/api/contracts/{cid}", headers=lawyer)).json()
    assert detail["status"] == "archived"


async def test_observer_cannot_archive(client, admin_headers):
    observer = await _make_user(
        client, admin_headers, "watch@test.uz", "watcher", "observer"
    )
    cid = await _make_contract(client, admin_headers)
    resp = await client.delete(f"/api/contracts/{cid}", headers=observer)
    assert resp.status_code == 403


async def test_final_status_reachable_without_finance_user(client, admin_headers):
    """Финансовое согласование добавлено сверх ТЗ. В организации без сотрудника
    с ролью «финансы» документ раньше не доходил до «Финального» вообще."""
    head = await _make_user(client, admin_headers, "head@test.uz", "head", "head")
    cid = await _make_contract(client, admin_headers)
    await _confirm_all(client, admin_headers, cid)
    await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=admin_headers
    )

    resp = await client.post(
        f"/api/contracts/{cid}/workflow/finalize", json={}, headers=head
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ready_to_sign"


# --------------------------------------------------------------------------
# Модули проверки
# --------------------------------------------------------------------------


async def test_risks_module_requires_party_side(client, admin_headers, mock_llm):
    """ТЗ: сторона меняет всю оптику анализа, без неё модуль не запускается."""
    cid = await _make_contract(client, admin_headers)

    resp = await client.post(
        f"/api/contracts/{cid}/review",
        json={"modules": ["risks"]},
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "сторону" in resp.json()["detail"]


async def test_review_rejects_unknown_module(client, admin_headers, mock_llm):
    cid = await _make_contract(client, admin_headers)
    resp = await client.post(
        f"/api/contracts/{cid}/review",
        json={"modules": ["module_x"]},
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_review_creates_runs_for_selected_modules(client, admin_headers, mock_llm):
    cid = await _make_contract(client, admin_headers)
    resp = await client.post(
        f"/api/contracts/{cid}/review",
        json={"modules": ["clauses", "logic"]},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    modules = {run["module"] for run in resp.json()}
    assert modules == {"clauses", "logic"}

    summary = (
        await client.get(f"/api/contracts/{cid}/review", headers=admin_headers)
    ).json()
    assert {module["module"] for module in summary["modules"]} == {
        "clauses",
        "logic",
        "risks",
    }
    assert summary["clauses"]["total"] > 0


async def test_review_without_api_key_returns_503(client, admin_headers, monkeypatch):
    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", "")
    cid = await _make_contract(client, admin_headers)

    resp = await client.post(
        f"/api/contracts/{cid}/review", json={"modules": ["clauses"]}, headers=admin_headers
    )
    assert resp.status_code == 503
    # Пункты при этом читаются: детерминированная часть работает без AI.
    assert (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).status_code == 200


# --------------------------------------------------------------------------
# Комментарии и роль «Наблюдатель»
# --------------------------------------------------------------------------


async def test_observer_can_comment_but_not_change_status(client, admin_headers):
    observer = await _make_user(
        client, admin_headers, "obs@test.uz", "observer1", "observer"
    )
    cid = await _make_contract(client, admin_headers)

    resp = await client.post(
        f"/api/contracts/{cid}/comments",
        json={"text": "Проверьте пункт об оплате"},
        headers=observer,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["author_role"] == "observer"

    resp = await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=observer
    )
    assert resp.status_code == 403

    comments = (
        await client.get(f"/api/contracts/{cid}/comments", headers=admin_headers)
    ).json()
    assert len(comments) == 1


async def test_comment_can_be_attached_to_clause(client, admin_headers):
    cid = await _make_contract(client, admin_headers)
    items = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]

    resp = await client.post(
        f"/api/contracts/{cid}/comments",
        json={"text": "Уточнить срок", "clause_id": items[0]["id"]},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["clause_anchor"] == items[0]["anchor"]


# --------------------------------------------------------------------------
# Версии, копия, экспорт
# --------------------------------------------------------------------------


async def test_version_diff_and_restore(client, admin_headers):
    cid = await _make_contract(client, admin_headers)
    await client.put(
        f"/api/contracts/{cid}",
        json={"content": CONTRACT_TEXT.replace("30 дней", "45 дней")},
        headers=admin_headers,
    )

    diff = (
        await client.get(
            f"/api/contracts/{cid}/versions/2/diff", headers=admin_headers
        )
    ).json()
    assert diff["from_version"] == 1 and diff["to_version"] == 2
    assert diff["summary"]["identical"] is False
    assert any(block["type"] == "replace" for block in diff["blocks"])

    resp = await client.post(
        f"/api/contracts/{cid}/versions/1/restore",
        json={"comment": "Вернуть исходную редакцию"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert "30 дней" in resp.json()["content"]

    versions = (
        await client.get(f"/api/contracts/{cid}/versions", headers=admin_headers)
    ).json()
    # Откат не стирает историю, а добавляет версию.
    assert len(versions) == 3


async def test_duplicate_contract_does_not_carry_decisions(client, admin_headers):
    cid = await _make_contract(client, admin_headers)
    await _confirm_all(client, admin_headers, cid)

    resp = await client.post(
        f"/api/contracts/{cid}/duplicate",
        json={"title": "Договор с другим покупателем", "counterparty": "ООО Бета"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    copy_id = resp.json()["id"]
    assert resp.json()["counterparty"] == "ООО Бета"
    assert resp.json()["status"] == "draft"

    payload = (
        await client.get(f"/api/contracts/{copy_id}/clauses", headers=admin_headers)
    ).json()
    assert payload["progress"]["total"] > 0
    assert payload["progress"]["resolved"] == 0


async def test_export_docx_clean_and_working(client, admin_headers):
    cid = await _make_contract(client, admin_headers)
    await client.post(
        f"/api/contracts/{cid}/comments",
        json={"text": "Внутреннее замечание для коллеги"},
        headers=admin_headers,
    )

    clean = await client.get(
        f"/api/contracts/{cid}/export?fmt=docx&mode=clean", headers=admin_headers
    )
    assert clean.status_code == 200, clean.text
    assert clean.headers["content-type"].startswith(
        "application/vnd.openxmlformats"
    )
    assert clean.content[:2] == b"PK"  # DOCX это zip

    working = await client.get(
        f"/api/contracts/{cid}/export?fmt=docx&mode=working", headers=admin_headers
    )
    assert working.status_code == 200
    # Рабочая версия крупнее: в ней разделы с замечаниями и комментариями.
    assert len(working.content) > len(clean.content)


async def test_export_denied_without_permission(client, admin_headers):
    external = await _make_user(
        client, admin_headers, "ext@test.uz", "ext1", "external"
    )
    cid = await _make_contract(client, admin_headers)

    resp = await client.get(
        f"/api/contracts/{cid}/export?fmt=docx", headers=external
    )
    assert resp.status_code == 403


# --------------------------------------------------------------------------
# База шаблонов
# --------------------------------------------------------------------------


async def test_template_lifecycle_and_verification(client, admin_headers):
    resp = await client.post(
        "/api/templates",
        json={
            "name": "Поставка оборудования",
            "doc_type": "supply",
            "content": CONTRACT_TEXT,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    template = resp.json()
    assert template["verified_at"] is None
    assert template["doc_type_title"] == "Договор поставки"

    verified = (
        await client.post(
            f"/api/templates/{template['id']}/verify", headers=admin_headers
        )
    ).json()
    assert verified["verified_at"] is not None
    assert verified["verified_by_name"]

    # Правка текста снимает верификацию: она относилась к прежней редакции.
    updated = (
        await client.patch(
            f"/api/templates/{template['id']}",
            json={"content": CONTRACT_TEXT + "\n4. ПРОЧЕЕ\n4.1. Условие."},
            headers=admin_headers,
        )
    ).json()
    assert updated["verified_at"] is None

    resp = await client.delete(
        f"/api/templates/{template['id']}", headers=admin_headers
    )
    assert resp.status_code == 204
    assert (await client.get("/api/templates", headers=admin_headers)).json() == []


async def test_template_verification_denied_for_lawyer(client, admin_headers):
    lawyer = await _make_user(client, admin_headers, "l9@test.uz", "l9", "lawyer")
    template = (
        await client.post(
            "/api/templates",
            json={"name": "Шаблон", "doc_type": "nda", "content": "1. Текст"},
            headers=lawyer,
        )
    ).json()

    resp = await client.post(
        f"/api/templates/{template['id']}/verify", headers=lawyer
    )
    assert resp.status_code == 403


async def test_save_as_template_requires_confirmed_document(client, admin_headers):
    cid = await _make_contract(client, admin_headers)

    resp = await client.post(
        f"/api/contracts/{cid}/save-as-template", json={}, headers=admin_headers
    )
    assert resp.status_code == 409

    await _confirm_all(client, admin_headers, cid)
    await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=admin_headers
    )
    resp = await client.post(
        f"/api/contracts/{cid}/save-as-template",
        json={"name": "Проверенный шаблон поставки"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "Проверенный шаблон поставки"


async def test_document_types_catalogue(client, admin_headers):
    types = (await client.get("/api/document-types", headers=admin_headers)).json()
    values = {item["value"] for item in types}

    # Каталог ТЗ, раздел 3.1
    assert {"supply", "service", "contracting", "lease", "purchase"} <= values
    assert {"employment", "nda", "license", "amendment"} <= values
    supply = next(item for item in types if item["value"] == "supply")
    assert "порядок приёмки товара" in supply["required_blocks"]


# --------------------------------------------------------------------------
# Контекст и участники проекта
# --------------------------------------------------------------------------


async def test_project_context_roundtrip(client, admin_headers):
    project = (
        await client.post(
            "/api/projects/", json={"name": "Сделка с Альфой"}, headers=admin_headers
        )
    ).json()

    resp = await client.put(
        f"/api/projects/{project['id']}/context",
        json={
            "our_party": "ООО «Альфа»",
            "counterparty": "ИП Петров",
            "amount": 500000000,
            "currency": "UZS",
            "jurisdiction": "Экономический суд г. Ташкента",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    context = (
        await client.get(f"/api/projects/{project['id']}/context", headers=admin_headers)
    ).json()
    assert context["our_party"] == "ООО «Альфа»"
    assert context["currency"] == "UZS"


async def test_project_members(client, admin_headers):
    lawyer = await _make_user(client, admin_headers, "pm@test.uz", "pm1", "lawyer")
    me = (await client.get("/api/auth/me", headers=lawyer)).json()
    project = (
        await client.post(
            "/api/projects/", json={"name": "Проект с участниками"}, headers=admin_headers
        )
    ).json()

    resp = await client.post(
        f"/api/projects/{project['id']}/members",
        json={"user_id": me["id"], "access": "comment"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["access"] == "comment"

    members = (
        await client.get(f"/api/projects/{project['id']}/members", headers=admin_headers)
    ).json()
    assert len(members) == 1

    resp = await client.delete(
        f"/api/projects/{project['id']}/members/{members[0]['id']}",
        headers=admin_headers,
    )
    assert resp.status_code == 204


# --------------------------------------------------------------------------
# Изоляция организаций
# --------------------------------------------------------------------------


async def test_foreign_org_cannot_read_clauses_or_comments(client, admin_headers):
    cid = await _make_contract(client, admin_headers)
    items = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]

    other = await register_and_login(
        client, email="other@test.uz", username="other"
    )
    await client.post(
        "/api/organizations/", json={"name": "ООО Чужая"}, headers=other
    )

    assert (
        await client.get(f"/api/contracts/{cid}/clauses", headers=other)
    ).status_code == 404
    assert (
        await client.get(f"/api/contracts/{cid}/comments", headers=other)
    ).status_code == 404
    assert (
        await client.get(f"/api/contracts/{cid}/export?fmt=docx", headers=other)
    ).status_code == 404
    resp = await client.post(
        f"/api/clauses/{items[0]['id']}/decision",
        json={"action": "confirm"},
        headers=other,
    )
    assert resp.status_code == 404


async def test_foreign_org_cannot_read_templates(client, admin_headers):
    template = (
        await client.post(
            "/api/templates",
            json={"name": "Наш шаблон", "doc_type": "nda", "content": "1. Текст"},
            headers=admin_headers,
        )
    ).json()

    other = await register_and_login(
        client, email="other2@test.uz", username="other2"
    )
    await client.post(
        "/api/organizations/", json={"name": "ООО Вторая"}, headers=other
    )

    assert (await client.get("/api/templates", headers=other)).json() == []
    assert (
        await client.get(f"/api/templates/{template['id']}", headers=other)
    ).status_code == 404


# --------------------------------------------------------------------------
# Разграничение доступа по участникам проекта (ТЗ, раздел 1)
# --------------------------------------------------------------------------


async def test_project_members_restrict_visibility(client, admin_headers):
    """Проект с участниками закрыт для тех, кого в него не добавили.

    До этой проверки поле access только хранилось: интерфейс показывал чип
    «Просмотр», а юрист с чужого дела видел все договоры организации.
    """
    outsider = await _make_user(
        client, admin_headers, "outsider@test.uz", "outsider", "lawyer"
    )
    insider = await _make_user(
        client, admin_headers, "insider@test.uz", "insider", "lawyer"
    )
    insider_me = (await client.get("/api/auth/me", headers=insider)).json()

    project = (
        await client.post(
            "/api/projects/", json={"name": "Дело клиента А"}, headers=admin_headers
        )
    ).json()
    resp = await client.post(
        f"/api/projects/{project['id']}/members",
        json={"user_id": insider_me["id"], "access": "write"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text

    contract = (
        await client.post(
            "/api/contracts/",
            json={
                "title": "Договор клиента А",
                "contract_type": "supply",
                "content": CONTRACT_TEXT,
                "project_id": project["id"],
            },
            headers=admin_headers,
        )
    ).json()

    # Чужой юрист не видит ни проект, ни документ — именно 404, а не 403:
    # существование чужого дела подтверждать нельзя.
    assert (
        await client.get(f"/api/projects/{project['id']}", headers=outsider)
    ).status_code == 404
    assert (
        await client.get(f"/api/contracts/{contract['id']}", headers=outsider)
    ).status_code == 404
    listed = (await client.get("/api/projects/", headers=outsider)).json()
    assert all(item["id"] != project["id"] for item in listed)

    # Участник проекта видит и проект, и документ.
    assert (
        await client.get(f"/api/projects/{project['id']}", headers=insider)
    ).status_code == 200

    # Руководителю ТЗ даёт доступ ко всем проектам.
    head = await _make_user(client, admin_headers, "boss@test.uz", "boss", "head")
    assert (
        await client.get(f"/api/projects/{project['id']}", headers=head)
    ).status_code == 200


async def test_project_without_members_stays_shared(client, admin_headers):
    """Проект без назначенных участников остаётся общим для организации."""
    lawyer = await _make_user(
        client, admin_headers, "shared@test.uz", "sharedone", "lawyer"
    )
    project = (
        await client.post(
            "/api/projects/", json={"name": "Общий проект"}, headers=admin_headers
        )
    ).json()

    assert (
        await client.get(f"/api/projects/{project['id']}", headers=lawyer)
    ).status_code == 200


# --------------------------------------------------------------------------
# Правка пункта не должна ломать структуру документа
# --------------------------------------------------------------------------

STRUCTURED_TEXT = """ДОГОВОР ПОСТАВКИ № 42

ООО «Альфа», именуемое «Поставщик», и ИП Петров, именуемый «Покупатель».

Раздел 1. ПРЕДМЕТ ДОГОВОРА
1.1. Поставщик обязуется поставить оборудование.
1.2. Покупатель обязан:
а) принять товар;
б) оплатить товар.

II. ОТВЕТСТВЕННОСТЬ СТОРОН
2.1. За просрочку начисляется пеня 0,1% в день.
"""


async def test_clause_edit_preserves_document_structure(client, admin_headers):
    """Правка пункта вставляется на место, а не пересобирает документ.

    Пересборка из пунктов теряла слово «Раздел», римскую нумерацию разделов и
    маркеры подпунктов, а на следующем разборе схлопывала подпункты в родителя
    вместе с подтверждениями юриста. Этот же текст уходил контрагенту.
    """
    cid = await _make_contract(client, admin_headers, content=STRUCTURED_TEXT)
    items = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]
    anchors_before = [item["anchor"] for item in items]
    assert "1.2.а" in anchors_before and "1.2.б" in anchors_before

    target = next(item for item in items if item["anchor"] == "2.1")
    resp = await client.post(
        f"/api/clauses/{target['id']}/decision",
        json={
            "action": "edit",
            "new_text": "За просрочку начисляется пеня 0,5% в день.",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    content = (
        await client.get(f"/api/contracts/{cid}", headers=admin_headers)
    ).json()["content"]

    assert "0,5%" in content, "правка не попала в текст"
    assert "Раздел 1." in content, "потеряно слово «Раздел»"
    assert "II. ОТВЕТСТВЕННОСТЬ" in content, "потеряна римская нумерация раздела"
    assert "а) принять товар;" in content, "потерян маркер подпункта «а)»"
    assert "б) оплатить товар." in content, "потерян маркер подпункта «б)»"
    assert "0,1%" not in content, "старая редакция осталась в тексте"

    # Повторный разбор даёт тот же набор якорей — решения юриста не теряются.
    after = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]
    assert [item["anchor"] for item in after] == anchors_before


async def test_clean_export_uses_document_text(client, admin_headers):
    """Контрагенту уходит текст договора, а не реконструкция из пунктов."""
    cid = await _make_contract(client, admin_headers, content=STRUCTURED_TEXT)
    resp = await client.get(
        f"/api/contracts/{cid}/export?fmt=docx&mode=clean", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text

    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    assert "Раздел 1." in xml
    assert "II. ОТВЕТСТВЕННОСТЬ" in xml
    assert "а) принять товар;" in xml


# --------------------------------------------------------------------------
# Устойчивость движка проверки: гонки, повторные запуски, сброс статуса
# --------------------------------------------------------------------------


async def _stuck_run(db_factory, cid: str, module: str):
    """Прогон, застрявший в «running», — состояние, которое надо пережить."""
    import uuid as _uuid

    from app.db.models import ReviewRun

    async with db_factory() as session:
        run = ReviewRun(
            contract_id=_uuid.UUID(cid),
            module=module,
            status="running",
        )
        session.add(run)
        await session.commit()
        return run.id


async def test_second_run_of_same_module_is_rejected(
    client, admin_headers, db_factory, mock_llm
):
    """Двойной клик по «Запустить проверку» задваивал находки: оба прогона
    гасили открытые замечания и вставляли свои."""
    cid = await _make_contract(client, admin_headers)
    await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    await _stuck_run(db_factory, cid, "logic")

    resp = await client.post(
        f"/api/contracts/{cid}/review",
        json={"modules": ["logic"]},
        headers=admin_headers,
    )
    assert resp.status_code == 400, resp.text
    assert "уже идёт" in resp.json()["detail"].lower()


async def test_other_module_still_starts_while_one_runs(
    client, admin_headers, db_factory, mock_llm
):
    """Запрет касается только того же модуля: ТЗ разрешает гонять их порознь."""
    cid = await _make_contract(client, admin_headers)
    await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    await _stuck_run(db_factory, cid, "logic")

    resp = await client.post(
        f"/api/contracts/{cid}/review",
        json={"modules": ["clauses"]},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text


async def test_edit_is_blocked_while_review_runs(client, admin_headers, db_factory):
    """Правка во время прогона рвала внешний ключ на пунктах: прогон падал,
    строка навсегда оставалась «running», документ висел в «На проверке»."""
    cid = await _make_contract(client, admin_headers)
    await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    await _stuck_run(db_factory, cid, "clauses")

    resp = await client.put(
        f"/api/contracts/{cid}",
        json={"content": "1. ПРЕДМЕТ\nДругой текст."},
        headers=admin_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "проверк" in resp.json()["detail"].lower()


async def test_one_finished_module_takes_document_out_of_analyzing(
    client, admin_headers, db_factory
):
    """ТЗ разрешает пройти один модуль. Раньше «На проверке» снималось только
    когда отработали все три — юрист упирался в запрет подтверждения."""
    import uuid as _uuid

    from app.db.models import Contract, ContractStatus, ReviewRun
    from app.services import review as review_service

    cid = await _make_contract(client, admin_headers)
    await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)

    async with db_factory() as session:
        contract = await session.get(Contract, _uuid.UUID(cid))
        contract.status = ContractStatus.ANALYZING.value
        session.add(
            ReviewRun(contract_id=contract.id, module="logic", status="done")
        )
        await session.flush()
        await review_service._sync_contract_status(session, contract)
        await session.commit()
        assert contract.status == ContractStatus.ANALYZED.value


async def test_failed_run_does_not_leave_document_in_analyzing(
    client, admin_headers, db_factory
):
    """Упавший прогон тоже снимает «На проверке»: иначе документ чинится
    только руками в базе."""
    import uuid as _uuid

    from app.db.models import Contract, ContractStatus, ReviewRun
    from app.services import review as review_service

    cid = await _make_contract(client, admin_headers)

    async with db_factory() as session:
        contract = await session.get(Contract, _uuid.UUID(cid))
        contract.status = ContractStatus.ANALYZING.value
        session.add(
            ReviewRun(contract_id=contract.id, module="clauses", status="failed")
        )
        await session.flush()
        await review_service._sync_contract_status(session, contract)
        await session.commit()
        assert contract.status != ContractStatus.ANALYZING.value


async def test_editing_approved_document_returns_it_to_revision(
    client, admin_headers
):
    """Иначе можно было подтвердить одну редакцию, переписать текст и пройти
    «Финальный» по непроверенной."""
    cid = await _make_contract(client, admin_headers)
    await _confirm_all(client, admin_headers, cid)
    approved = await client.post(
        f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=admin_headers
    )
    assert approved.json()["status"] == "approved"

    resp = await client.put(
        f"/api/contracts/{cid}",
        json={"content": CONTRACT_TEXT + "\n\n5. ДОПОЛНИТЕЛЬНО\n5.1. Новый пункт."},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "needs_revision"


async def test_ai_generated_document_gets_generated_status(client, admin_headers):
    """ТЗ, раздел 3.1: сгенерированный черновик отличим от заведённого руками."""
    resp = await client.post(
        "/api/contracts/",
        json={
            "title": "Сгенерированный договор",
            "contract_type": "supply",
            "content": CONTRACT_TEXT,
            "ai_generated": True,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "generated"

    manual = await client.post(
        "/api/contracts/",
        json={
            "title": "Заведён руками",
            "contract_type": "supply",
            "content": CONTRACT_TEXT,
        },
        headers=admin_headers,
    )
    assert manual.json()["status"] == "draft"


# --------------------------------------------------------------------------
# Журнал действий, заморозка замечаний, разбор загруженного документа
# --------------------------------------------------------------------------


async def test_audit_trail_shows_who_did_what(client, admin_headers):
    """ТЗ, раздел 5: решение юриста фиксируется с автором и временем — и это
    должно быть видно. Записи писались с начала, но прочитать их было нечем."""
    cid = await _make_contract(client, admin_headers)
    items = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]
    await client.post(
        f"/api/clauses/{items[0]['id']}/decision",
        json={"action": "confirm"},
        headers=admin_headers,
    )

    resp = await client.get(f"/api/contracts/{cid}/audit", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    page = resp.json()
    actions = [entry["action"] for entry in page["items"]]
    assert "contract_created" in actions
    assert "clause_decision" in actions
    assert page["total"] >= 2

    decision = next(e for e in page["items"] if e["action"] == "clause_decision")
    assert decision["title"] == "Решение по пункту"
    assert decision["author_name"]
    assert items[0]["anchor"] in (decision["detail"] or "")


async def test_audit_trail_is_isolated_between_organizations(client, admin_headers):
    cid = await _make_contract(client, admin_headers)
    other = await register_and_login(
        client, email="audit-other@test.uz", username="audit-other"
    )
    await client.post(
        "/api/organizations/", json={"name": "ООО Посторонняя"}, headers=other
    )
    resp = await client.get(f"/api/contracts/{cid}/audit", headers=other)
    assert resp.status_code == 404


async def test_findings_freeze_on_closed_document(client, admin_headers, db_factory):
    """Отметка «риск устранён» после подписания переписывает историю проверки."""
    import uuid as _uuid

    from app.db.models import Contract, ContractStatus, RiskFinding

    cid = await _make_contract(client, admin_headers)
    async with db_factory() as session:
        finding = RiskFinding(
            contract_id=_uuid.UUID(cid),
            category="financial",
            level="high",
            description="Неограниченная неустойка",
        )
        session.add(finding)
        contract = await session.get(Contract, _uuid.UUID(cid))
        contract.status = ContractStatus.SIGNED.value
        await session.commit()
        finding_id = str(finding.id)

    resp = await client.patch(
        f"/api/risk-findings/{finding_id}",
        json={"status": "fixed"},
        headers=admin_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "закрыт" in resp.json()["detail"].lower()

    # Комментарий при этом оставить можно: заметка на подписанном документе —
    # обычная работа, а не переписывание истории проверки.
    comment = await client.post(
        f"/api/contracts/{cid}/comments",
        json={"text": "Расторгнут по соглашению сторон"},
        headers=admin_headers,
    )
    assert comment.status_code == 201, comment.text


async def test_module_three_summary_is_stored_and_returned(
    client, admin_headers, db_factory
):
    """ТЗ, раздел 4: «что критично поправить до подписания». Резюме модель
    возвращала, но оно нигде не сохранялось."""
    import uuid as _uuid

    from app.db.models import ReviewRun

    cid = await _make_contract(client, admin_headers)
    async with db_factory() as session:
        session.add(
            ReviewRun(
                contract_id=_uuid.UUID(cid),
                module="risks",
                status="done",
                party_side="Поставщик",
                summary="До подписания ограничить неустойку и убрать одностороннее расторжение.",
            )
        )
        await session.commit()

    summary = (
        await client.get(f"/api/contracts/{cid}/review", headers=admin_headers)
    ).json()
    assert "ограничить неустойку" in summary["risks"]["summary"]


async def test_uploaded_document_arrives_split_into_clauses(client, admin_headers):
    """ТЗ, 3.2: система разбирает загруженный документ в структуру. Разбивка
    детерминированная, поэтому делается сразу и не требует ключа API."""
    files = {"file": ("dogovor.txt", CONTRACT_TEXT.encode("utf-8"), "text/plain")}
    resp = await client.post(
        "/api/contracts/upload",
        data={"title": "Входящий договор", "contract_type": "supply"},
        files=files,
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    cid = resp.json()["id"]

    clauses = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()
    assert clauses["progress"]["total"] > 0
    assert "1.1" in [item["anchor"] for item in clauses["items"]]


async def test_verdict_goes_stale_when_clause_text_changes(
    client, admin_headers, db_factory
):
    """Юрист правил пункт и продолжал видеть «соответствует», вынесенное по
    прежней редакции: у вердикта не было хеша текста."""
    import uuid as _uuid

    from app.db.models import Clause, ClauseCheck

    cid = await _make_contract(client, admin_headers)
    items = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]
    target = next(item for item in items if item["anchor"] == "1.1")

    async with db_factory() as session:
        clause = await session.get(Clause, _uuid.UUID(target["id"]))
        session.add(
            ClauseCheck(
                clause_id=clause.id,
                verdict="complies",
                rationale="Соответствует статье 353 ГК.",
                sources=[],
                clause_hash=clause.content_hash,
            )
        )
        await session.commit()

    before = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]
    assert next(i for i in before if i["anchor"] == "1.1")["check"]["stale"] is False

    await client.post(
        f"/api/clauses/{target['id']}/decision",
        json={"action": "edit", "new_text": "Поставщик передаёт товар в срок 10 дней."},
        headers=admin_headers,
    )

    after = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]
    changed = next(i for i in after if i["anchor"] == "1.1")
    assert changed["check"] is not None
    assert changed["check"]["stale"] is True


async def test_verdicts_survive_edit_of_another_clause(
    client, admin_headers, db_factory
):
    """Правка одного пункта стирала результат сверки по всему документу.

    Дерево пунктов при пересборке удаляется целиком, а `clause_checks` висят
    на пункте каскадом — переносились только решения юриста. Юрист правил один
    пункт и терял вердикты по всем остальным, а Модуль 1 приходилось гонять
    заново за счёт дневной квоты токенов организации.
    """
    import uuid as _uuid

    from app.db.models import Clause, ClauseCheck

    cid = await _make_contract(client, admin_headers)
    items = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]
    edited = next(item for item in items if item["anchor"] == "1.1")
    untouched = next(item for item in items if item["anchor"] == "2.1")

    async with db_factory() as session:
        for item in (edited, untouched):
            clause = await session.get(Clause, _uuid.UUID(item["id"]))
            session.add(
                ClauseCheck(
                    clause_id=clause.id,
                    verdict="complies",
                    rationale="Соответствует норме.",
                    sources=[],
                    clause_hash=clause.content_hash,
                )
            )
        await session.commit()

    await client.post(
        f"/api/clauses/{edited['id']}/decision",
        json={"action": "edit", "new_text": "Поставщик передаёт товар в срок 10 дней."},
        headers=admin_headers,
    )

    after = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]
    kept = next(item for item in after if item["anchor"] == "2.1")
    assert kept["check"] is not None, "вердикт по нетронутому пункту потерян"
    assert kept["check"]["verdict"] == "complies"
    assert kept["check"]["stale"] is False, "текст пункта не менялся"

    changed = next(item for item in after if item["anchor"] == "1.1")
    assert changed["check"]["stale"] is True


# --------------------------------------------------------------------------
# Параллельные прогоны и накопление вердиктов
# --------------------------------------------------------------------------


async def test_parallel_runs_do_not_strand_document_in_analyzing(
    client, admin_headers, db_factory
):
    """Три модуля, финиширующие в одном окне, оставляли документ в «На проверке».

    Каждый прогон работает в своей сессии, и собственный `status="done"` к
    моменту подсчёта ещё не закоммичен. Без блокировки строки договора все три
    видят друг друга как «running» и ни один не снимает статус. Подтвердить
    документ из «На проверке» нельзя — чинилось только руками в БД.
    """
    import asyncio
    import uuid as _uuid

    from app.db.models import Contract, ContractStatus, ReviewRun
    from app.services import review as review_service

    cid = await _make_contract(client, admin_headers)
    await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)

    run_ids = []
    async with db_factory() as session:
        contract = await session.get(Contract, _uuid.UUID(cid))
        contract.status = ContractStatus.ANALYZING.value
        for module in ("clauses", "logic", "risks"):
            run = ReviewRun(
                contract_id=contract.id, module=module, status="running"
            )
            session.add(run)
            await session.flush()
            run_ids.append(run.id)
        await session.commit()

    async def finish(run_id):
        """Повторяет хвост perform_run: свой прогон done, затем синхронизация."""
        async with db_factory() as session:
            run = await session.get(ReviewRun, run_id)
            run.status = "done"
            contract = await session.get(Contract, run.contract_id)
            await review_service._sync_contract_status(session, contract)
            await session.commit()

    # Одновременно, как это и происходит при запуске всех трёх модулей сразу.
    await asyncio.gather(*(finish(run_id) for run_id in run_ids))

    async with db_factory() as session:
        contract = await session.get(Contract, _uuid.UUID(cid))
        assert contract.status == ContractStatus.ANALYZED.value, (
            "документ завис в «На проверке»: ни один из параллельных прогонов "
            "не снял статус"
        )


async def test_rebuild_and_restore_are_blocked_during_review(
    client, admin_headers, db_factory
):
    """Пересборка пунктов и откат версии тоже роняли идущий прогон.

    Защита стояла только на правке текста документа, а дерево пунктов удаляют
    ещё три пути: кнопка «Пересобрать», действие «Изменить» по пункту и откат
    к прежней версии. Фоновая задача держит старые строки пунктов в памяти и
    падает на внешнем ключе, когда их удаляют.
    """
    import uuid as _uuid

    from app.db.models import ReviewRun

    cid = await _make_contract(client, admin_headers)
    items = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]

    async with db_factory() as session:
        session.add(
            ReviewRun(
                contract_id=_uuid.UUID(cid), module="clauses", status="running"
            )
        )
        await session.commit()

    rebuild = await client.post(
        f"/api/contracts/{cid}/clauses/rebuild", headers=admin_headers
    )
    assert rebuild.status_code == 409, rebuild.text

    edit = await client.post(
        f"/api/clauses/{items[0]['id']}/decision",
        json={"action": "edit", "new_text": "Другая формулировка."},
        headers=admin_headers,
    )
    assert edit.status_code == 409, edit.text

    restore = await client.post(
        f"/api/contracts/{cid}/versions/1/restore",
        json={"comment": "откат"},
        headers=admin_headers,
    )
    assert restore.status_code == 409, restore.text

    # Действия, которые текста не трогают, во время прогона разрешены:
    # юрист продолжает проходить пункты, пока модель работает.
    confirm = await client.post(
        f"/api/clauses/{items[0]['id']}/decision",
        json={"action": "confirm"},
        headers=admin_headers,
    )
    assert confirm.status_code == 200, confirm.text


async def test_repeated_module_one_run_does_not_pile_up_verdicts(
    client, admin_headers, db_factory, mock_llm
):
    """Каждый повторный прогон Модуля 1 добавлял ещё по вердикту на пункт.

    Модули 2 и 3 перед вставкой чистят прежние находки, Модуль 1 — не чистил.
    Выборка «последнего вердикта» тянула из базы всю накопленную историю, и
    каждый следующий прогон делал экран проверки медленнее.
    """
    import uuid as _uuid

    from sqlalchemy import func, select

    from app.db.models import Clause, ClauseCheck, Contract, ReviewRun
    from app.services import review as review_service

    cid = await _make_contract(client, admin_headers)
    items = (
        await client.get(f"/api/contracts/{cid}/clauses", headers=admin_headers)
    ).json()["items"]

    async def count_checks(session):
        ids = (
            await session.execute(
                select(Clause.id).where(Clause.contract_id == _uuid.UUID(cid))
            )
        ).scalars().all()
        return (
            await session.execute(
                select(func.count(ClauseCheck.id)).where(ClauseCheck.clause_id.in_(ids))
            )
        ).scalar_one()

    async with db_factory() as session:
        # Прошлый прогон оставил по вердикту на каждый пункт.
        clauses = (
            await session.execute(
                select(Clause).where(Clause.contract_id == _uuid.UUID(cid))
            )
        ).scalars().all()
        for clause in clauses:
            session.add(
                ClauseCheck(
                    clause_id=clause.id,
                    verdict="complies",
                    rationale="Вердикт прошлого прогона.",
                    sources=[],
                    clause_hash=clause.content_hash,
                )
            )
        await session.commit()
        assert await count_checks(session) == len(items)

    async with db_factory() as session:
        contract = await session.get(Contract, _uuid.UUID(cid))
        run = ReviewRun(contract_id=contract.id, module="clauses", status="running")
        session.add(run)
        await session.flush()
        await review_service._run_clauses(session, contract, run)
        await session.commit()
        after = await count_checks(session)

    assert after <= len(items), (
        f"после повторного прогона вердиктов {after} при {len(items)} пунктах — "
        "история копится и утяжеляет каждую выборку"
    )
