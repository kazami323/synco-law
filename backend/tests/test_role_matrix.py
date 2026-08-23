"""Исполняемая матрица «роль × функция» — финальная проверка перед выкладкой
на боевой стенд, где начнут работать живые юристы.

Точечные тесты (test_workflow.py, test_legal_engine.py, test_security_features.py)
уже проверяют права по одному действию за раз. Этого недостаточно: правка
`ROLE_PERMISSIONS` в будущем может тихо расширить доступ одной роли — и
точечный тест этого не заметит, если не бьёт именно по этой клетке матрицы.
Этот файл проходит по всем восьми ролям (`app/db/models.Role`) и всем
значимым действиям над документом и фиксирует ожидаемый результат по каждой
клетке.

Источник ожиданий — ТЗ (docs/FUNCTIONAL_SPEC.md, разделы 2 и 7), а не текущий
код:

* Юрист, Старший юрист/руководитель, Наблюдатель, Администратор — роли ТЗ,
  ожидания взяты из раздела 7 (и раздела 2 — «кто ставит статус»).
* compliance, finance, external в ТЗ не описаны вовсе — это расширения
  продукта (docs/SPEC_GAP_ANALYSIS.md, раздел «7. Роли и права»). Для них
  ожидания взяты из документированного поведения `ROLE_PERMISSIONS`.

Матрица (+ разрешено, − запрещено). «сверх ТЗ» отмечает осознанное расширение
матрицы за пределы ТЗ — см. `test_head_manages_staff_as_deliberate_extension`
и SPEC_GAP_ANALYSIS.md.

               | create edit archive run_review confirm_clause comment export
admin          |   +     +     +        +            +           +      +
head           |   +     +     +        +            +           +      +
senior_lawyer  |   +     +     +        +            +           +      +
lawyer         |   +     +     +        +            +           +      +
compliance     |   −     −     −        −            −           +      −
finance        |   −     −     −        −            −           +      −
observer       |   −     −     −        −            −           +      −
external       |   −     −     −        −            −           −      −

               | approve_legal approve_finance finalize reject sign manage_templates verify_template manage_users
admin          |      +              +            +        +    +          +               +               +
head           |      +              −            +        +    −          +               +          + (сверх ТЗ)
senior_lawyer  |      +              −            +        +    −          +               +               −
lawyer         |      +              −            −        +    −          +               −               −
compliance     |      −              −            −        −    −          −               −               −
finance        |      −              +            −        +    −          −               −               −
observer       |      −              −            −        −    −          −               −               −
external       |      −              −            −        −    −          −               −               −

Плашки (`PUT`/`DELETE /api/contracts/{id}/labels/{kind}`) идут по праву
`edit` — тот же столбец, что «edit» выше (продуктовое решение, ТЗ плашки не
описывает).
"""

from __future__ import annotations

import uuid

import pytest

from app.db.models import LogicFinding, RiskFinding
from tests.conftest import register_and_login
from tests.test_legal_engine import CONTRACT_TEXT, _make_contract, _make_user, mock_llm  # noqa: F401

# Роли ТЗ (admin/head/senior_lawyer/lawyer/observer) + продуктовые расширения
# (compliance/finance/external) — полный enum Role из models.py.
ALL_ROLES = [
    "admin",
    "head",
    "senior_lawyer",
    "lawyer",
    "compliance",
    "finance",
    "observer",
    "external",
]

# ТЗ, раздел 7: юрист и оба «старших» — работают с документом целиком:
# заводят, правят, архивируют, запускают проверки, подтверждают пункты,
# экспортируют. Наблюдатель и продуктовые роли (compliance/finance/external)
# документ не ведут — только смотрят и где-то комментируют.
CAN_CREATE = {"admin", "head", "senior_lawyer", "lawyer"}

# ТЗ, раздел 7: «Наблюдатель — просмотр и комментирование». compliance и
# finance в коде получили то же «смотреть и комментировать» плюс своё
# специфичное право согласования (approve_compliance/approve_finance,
# ни одно из которых сейчас не привязано к другому эндпоинту, кроме
# workflow/approve_finance). external — read-only без комментариев.
COMMENT_ALLOWED = {"admin", "head", "senior_lawyer", "lawyer", "compliance", "finance", "observer"}

# get_visible_contract: кто видит любой документ организации, а не только
# созданный самим собой.
VIEW_ALL_ROLES = {"admin", "head", "senior_lawyer", "compliance", "finance", "observer"}

# ТЗ, раздел 2: «Финальный» — старший юрист или руководитель (раздел 7
# объединяет их одной строкой «Старший юрист / руководитель»).
FINALIZE_ALLOWED = {"admin", "head", "senior_lawyer"}

# Финансовое согласование — надстройка сверх ТЗ (SPEC_GAP_ANALYSIS.md,
# раздел 2: «Сверх ТЗ сохранены approved_finance и signed»). Право есть
# только у той роли, что и предназначена для него, плюс у админа.
APPROVE_FINANCE_ALLOWED = {"admin", "finance"}

# workflow.py: reject открыт любому, кто способен хоть на какое-то
# согласование (approve/approve_finance/finalize/sign).
REJECT_ALLOWED = {"admin", "head", "senior_lawyer", "lawyer", "finance"}

# E-IMZO подписание — тоже надстройка сверх ТЗ. В `ROLE_PERMISSIONS`
# буквальное право `sign` есть только у admin.
SIGN_ALLOWED = {"admin"}

# ТЗ, раздел 7: verify_template — «Старший юрист / руководитель», не юрист.
VERIFY_TEMPLATE_ALLOWED = {"admin", "head", "senior_lawyer"}


async def _headers_for(client, admin_headers, role: str, *, prefix: str = "m") -> dict:
    if role == "admin":
        return admin_headers
    return await _make_user(
        client, admin_headers, f"{prefix}-{role}@matrix.uz", f"{prefix}-{role}", role
    )


@pytest.fixture
async def roster(client, admin_headers):
    """По одному пользователю на каждую роль организации."""
    return {role: await _headers_for(client, admin_headers, role) for role in ALL_ROLES}


@pytest.fixture
async def own_docs(client, roster):
    """Документ, созданный каждой ролью, которая по ТЗ вправе это делать."""
    return {
        role: await _make_contract(client, roster[role], title=f"Договор роли {role}")
        for role in CAN_CREATE
    }


@pytest.fixture
async def shared_doc(client, admin_headers):
    """Документ администратора — «чужой» для всех остальных ролей."""
    return await _make_contract(client, admin_headers, title="Общий документ администратора")


@pytest.fixture
async def other_org_roster(client):
    """По одному пользователю на каждую роль — но в ДРУГОЙ организации.

    Нужен для проверки межорганизационной изоляции: ни одна роль, независимо
    от набора прав, не должна получить доступ к документу чужой организации.
    """
    other_admin = await register_and_login(
        client, email="matrix-admin@other.uz", username="matrix-admin"
    )
    resp = await client.post(
        "/api/organizations/", json={"name": "ООО Чужая (матрица)"}, headers=other_admin
    )
    assert resp.status_code == 201, resp.text

    roster = {"admin": other_admin}
    for role in ALL_ROLES:
        if role == "admin":
            continue
        roster[role] = await _headers_for(client, other_admin, role, prefix="o")
    return roster


async def _first_clause_id(client, headers, contract_id: str) -> str:
    resp = await client.get(f"/api/contracts/{contract_id}/clauses", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["items"][0]["id"]


async def _prep_workflow_contract(client, roster, role: str, target_status: str) -> str:
    """Документ в нужном статусе-предшественнике для проверки перехода.

    Документ заводится и НЕ проходит через `GET /clauses`: пока пункты не
    разобраны, `_ensure_clauses_confirmed` пропускает гейт (progress.total ==
    0). Это тот же приём, что в test_workflow.py — здесь проверяются права на
    переход, а не блокирующее правило по пунктам (оно покрыто отдельно в
    test_legal_engine.py).
    """
    owner_headers = roster[role] if role in CAN_CREATE else roster["admin"]
    cid = await _make_contract(client, owner_headers, title=f"WF {role} -> {target_status}")
    admin_headers = roster["admin"]
    if target_status in ("approved", "ready_to_sign"):
        resp = await client.post(
            f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=admin_headers
        )
        assert resp.status_code == 200, resp.text
    if target_status == "ready_to_sign":
        resp = await client.post(
            f"/api/contracts/{cid}/workflow/finalize", json={}, headers=admin_headers
        )
        assert resp.status_code == 200, resp.text
    return cid


# --------------------------------------------------------------------------
# Создание, правка, архивация
# --------------------------------------------------------------------------


async def test_create_matrix(client, roster):
    """ТЗ, раздел 7: документ заводит юрист и оба «старших»; администратор —
    по умолчанию может всё. Остальные роли документ не ведут."""
    for role, headers in roster.items():
        resp = await client.post(
            "/api/contracts/",
            json={"title": f"Договор ({role})", "contract_type": "supply", "content": "Текст"},
            headers=headers,
        )
        if role in CAN_CREATE:
            assert resp.status_code == 201, (
                f"роль {role}: создание документа должно быть разрешено (ТЗ, раздел 7), "
                f"получили {resp.status_code}: {resp.text}"
            )
        else:
            assert resp.status_code == 403, (
                f"роль {role}: создание документа должно быть запрещено, "
                f"получили {resp.status_code}: {resp.text}"
            )


async def test_edit_and_archive_matrix(client, roster, own_docs, shared_doc):
    """ТЗ, раздел 2: «В архиве» ставит юрист; правка текста — часть работы
    над документом, которую ТЗ (раздел 7) отдаёт тем же ролям."""
    for role, headers in roster.items():
        if role in CAN_CREATE:
            cid = own_docs[role]
            resp = await client.put(
                f"/api/contracts/{cid}",
                json={"content": CONTRACT_TEXT + f"\n\nПравка роли {role}."},
                headers=headers,
            )
            assert resp.status_code == 200, (
                f"роль {role}: правка своего документа должна быть разрешена, "
                f"получили {resp.status_code}: {resp.text}"
            )

            resp = await client.delete(f"/api/contracts/{cid}", headers=headers)
            assert resp.status_code == 200, (
                f"роль {role}: архивация своего документа должна быть разрешена "
                f"(ТЗ, раздел 2 — статус «В архиве» ставит юрист), "
                f"получили {resp.status_code}: {resp.text}"
            )
        else:
            resp = await client.put(
                f"/api/contracts/{shared_doc}",
                json={"content": "Попытка правки чужого текста"},
                headers=headers,
            )
            assert resp.status_code == 403, (
                f"роль {role}: правка чужого документа должна быть запрещена, "
                f"получили {resp.status_code}: {resp.text}"
            )

            resp = await client.delete(f"/api/contracts/{shared_doc}", headers=headers)
            assert resp.status_code == 403, (
                f"роль {role}: архивация чужого документа должна быть запрещена, "
                f"получили {resp.status_code}: {resp.text}"
            )


# --------------------------------------------------------------------------
# Чтение: список, своя карточка, чужая карточка, чужая организация
# --------------------------------------------------------------------------


async def test_read_list_matrix(client, roster, own_docs, shared_doc):
    """Список документов доступен всем ролям (у каждой есть либо `view_all`,
    либо `view_assigned»), но юрист видит в нём только свои документы —
    иначе конфликт интересов между делами разных клиентов (ТЗ, раздел 1)."""
    for role, headers in roster.items():
        resp = await client.get("/api/contracts/", headers=headers)
        assert resp.status_code == 200, (
            f"роль {role}: список документов должен быть доступен, "
            f"получили {resp.status_code}: {resp.text}"
        )

    lawyer_items = (
        await client.get("/api/contracts/", headers=roster["lawyer"])
    ).json()["items"]
    lawyer_ids = {item["id"] for item in lawyer_items}
    assert own_docs["lawyer"] in lawyer_ids, "юрист должен видеть свой документ в списке"
    assert shared_doc not in lawyer_ids, (
        "юрист не должен видеть в общем списке документ, который завёл кто-то другой "
        "(view_assigned — только свои)"
    )
    assert own_docs["admin"] not in lawyer_ids


async def test_read_card_matrix(client, roster, own_docs, shared_doc):
    """Своя карточка видна всегда. Чужая карточка ВНУТРИ организации — по
    `view_all`: у кого его нет, получает 403 (документ существует, но не для
    него), а не 404 — скрывать факт существования внутри своей организации
    не нужно. 404 зарезервировано за межорганизационной изоляцией
    (test_foreign_org_cannot_read_any_role ниже)."""
    for role in CAN_CREATE:
        resp = await client.get(f"/api/contracts/{own_docs[role]}", headers=roster[role])
        assert resp.status_code == 200, (
            f"роль {role}: своя карточка документа должна быть видна, "
            f"получили {resp.status_code}: {resp.text}"
        )

    for role, headers in roster.items():
        resp = await client.get(f"/api/contracts/{shared_doc}", headers=headers)
        if role in VIEW_ALL_ROLES:
            assert resp.status_code == 200, (
                f"роль {role}: карточка чужого документа своей организации должна быть "
                f"видна (view_all), получили {resp.status_code}: {resp.text}"
            )
        else:
            assert resp.status_code == 403, (
                f"роль {role}: карточка чужого документа не должна быть видна "
                f"(нет view_all), получили {resp.status_code}"
            )


async def test_foreign_org_cannot_read_any_role(client, admin_headers, other_org_roster):
    """Изоляция организаций не зависит от роли: 404, а не 403 — иначе ответ
    сам подтверждает, что документ вообще существует."""
    cid = await _make_contract(client, admin_headers, title="Документ первой организации")
    for role, headers in other_org_roster.items():
        resp = await client.get(f"/api/contracts/{cid}", headers=headers)
        assert resp.status_code == 404, (
            f"роль {role} из чужой организации: изоляция должна отдавать 404, "
            f"получили {resp.status_code} — нельзя подтверждать существование чужого документа"
        )


# --------------------------------------------------------------------------
# Модули проверки и подтверждение пунктов
# --------------------------------------------------------------------------


async def test_run_review_matrix(client, roster, own_docs, shared_doc, mock_llm):
    """ТЗ, раздел 7: запуск проверок — право юриста и обоих «старших»."""
    for role, headers in roster.items():
        if role in CAN_CREATE:
            resp = await client.post(
                f"/api/contracts/{own_docs[role]}/review",
                json={"modules": ["clauses"]},
                headers=headers,
            )
            assert resp.status_code == 200, (
                f"роль {role}: запуск проверки должен быть разрешён (ТЗ, раздел 7), "
                f"получили {resp.status_code}: {resp.text}"
            )
        else:
            resp = await client.post(
                f"/api/contracts/{shared_doc}/review",
                json={"modules": ["clauses"]},
                headers=headers,
            )
            assert resp.status_code == 403, (
                f"роль {role}: запуск проверки должен быть запрещён, "
                f"получили {resp.status_code}: {resp.text}"
            )


async def test_confirm_clause_matrix(client, roster, own_docs, shared_doc):
    """ТЗ, раздел 4: решение по пункту принимает юрист (и оба «старших»),
    остальным ролям — включая наблюдателя — движок пунктов недоступен."""
    shared_clause_id = await _first_clause_id(client, roster["admin"], shared_doc)

    for role, headers in roster.items():
        if role in CAN_CREATE:
            clause_id = await _first_clause_id(client, headers, own_docs[role])
            resp = await client.post(
                f"/api/clauses/{clause_id}/decision",
                json={"action": "confirm"},
                headers=headers,
            )
            assert resp.status_code == 200, (
                f"роль {role}: подтверждение пункта должно быть разрешено, "
                f"получили {resp.status_code}: {resp.text}"
            )
        else:
            resp = await client.post(
                f"/api/clauses/{shared_clause_id}/decision",
                json={"action": "confirm"},
                headers=headers,
            )
            assert resp.status_code == 403, (
                f"роль {role}: подтверждение пункта должно быть запрещено, "
                f"получили {resp.status_code}: {resp.text}"
            )


async def test_finding_resolution_matrix(client, roster, own_docs, shared_doc, db_factory):
    """Решения по находкам Модулей 2 и 3 (`PATCH .../logic-findings`,
    `.../risk-findings`) защищены тем же правом, что и подтверждение пункта:
    юрист разбирает находки движка, наблюдатель и продуктовые роли — нет."""

    async def _seed(cid: str) -> tuple[str, str]:
        async with db_factory() as session:
            logic = LogicFinding(
                contract_id=uuid.UUID(cid),
                category="deadlines",
                description="В пунктах указаны разные сроки поставки",
                clause_anchors=["1.1", "3.1"],
            )
            risk = RiskFinding(
                contract_id=uuid.UUID(cid),
                category="financial",
                level="high",
                description="Неустойка ничем не ограничена",
            )
            session.add_all([logic, risk])
            await session.commit()
            return str(logic.id), str(risk.id)

    shared_logic_id, shared_risk_id = await _seed(shared_doc)

    for role, headers in roster.items():
        if role in CAN_CREATE:
            logic_id, risk_id = await _seed(own_docs[role])
            for finding_id, path in ((logic_id, "logic-findings"), (risk_id, "risk-findings")):
                resp = await client.patch(
                    f"/api/{path}/{finding_id}", json={"status": "accepted"}, headers=headers
                )
                assert resp.status_code == 200, (
                    f"роль {role}: решение по находке ({path}) должно быть разрешено, "
                    f"получили {resp.status_code}: {resp.text}"
                )
        else:
            for finding_id, path in (
                (shared_logic_id, "logic-findings"),
                (shared_risk_id, "risk-findings"),
            ):
                resp = await client.patch(
                    f"/api/{path}/{finding_id}", json={"status": "accepted"}, headers=headers
                )
                assert resp.status_code == 403, (
                    f"роль {role}: решение по находке ({path}) должно быть запрещено, "
                    f"получили {resp.status_code}: {resp.text}"
                )


# --------------------------------------------------------------------------
# Комментарии (ТЗ, раздел 7: даже наблюдатель может их оставлять)
# --------------------------------------------------------------------------


async def test_comment_matrix(client, roster, own_docs, shared_doc):
    for role, headers in roster.items():
        target = own_docs[role] if role in CAN_CREATE else shared_doc
        resp = await client.post(
            f"/api/contracts/{target}/comments",
            json={"text": f"Комментарий роли {role}"},
            headers=headers,
        )
        if role in COMMENT_ALLOWED:
            assert resp.status_code == 201, (
                f"роль {role}: комментирование должно быть разрешено "
                f"(ТЗ, раздел 7 — даже наблюдателю), получили {resp.status_code}: {resp.text}"
            )
        else:
            assert resp.status_code == 403, (
                f"роль {role}: комментирование должно быть запрещено, "
                f"получили {resp.status_code}: {resp.text}"
            )


# --------------------------------------------------------------------------
# Экспорт
# --------------------------------------------------------------------------


async def test_export_matrix(client, roster, own_docs, shared_doc):
    """ТЗ, раздел 7: экспорт — право юриста и обоих «старших»."""
    for role, headers in roster.items():
        target = own_docs[role] if role in CAN_CREATE else shared_doc
        resp = await client.get(f"/api/contracts/{target}/export?fmt=docx&mode=clean", headers=headers)
        if role in CAN_CREATE:
            assert resp.status_code == 200, (
                f"роль {role}: экспорт документа должен быть разрешён (ТЗ, раздел 7), "
                f"получили {resp.status_code}: {resp.text}"
            )
        else:
            assert resp.status_code == 403, (
                f"роль {role}: экспорт документа должен быть запрещён, "
                f"получили {resp.status_code}: {resp.text}"
            )


# --------------------------------------------------------------------------
# Журнал действий (ТЗ, раздел 5)
# --------------------------------------------------------------------------


async def test_audit_log_matrix(client, roster, own_docs, shared_doc):
    """Журнал доступен тому, кто видит сам документ (audit.py опирается на
    get_visible_contract) — отдельного права на чтение журнала нет."""
    for role, headers in roster.items():
        if role in CAN_CREATE:
            resp = await client.get(f"/api/contracts/{own_docs[role]}/audit", headers=headers)
            assert resp.status_code == 200, (
                f"роль {role}: журнал своего документа должен быть виден, "
                f"получили {resp.status_code}: {resp.text}"
            )
        else:
            resp = await client.get(f"/api/contracts/{shared_doc}/audit", headers=headers)
            expected = 200 if role in VIEW_ALL_ROLES else 403
            assert resp.status_code == expected, (
                f"роль {role}: журнал чужого документа своей организации — ожидали "
                f"{expected}, получили {resp.status_code}"
            )


# --------------------------------------------------------------------------
# Плашки — право `edit` (продуктовое решение, вне ТЗ)
# --------------------------------------------------------------------------


async def test_labels_matrix(client, roster, own_docs, shared_doc):
    for role, headers in roster.items():
        target = own_docs[role] if role in CAN_CREATE else shared_doc
        resp = await client.put(f"/api/contracts/{target}/labels/prepared", json={}, headers=headers)
        if role in CAN_CREATE:
            assert resp.status_code == 200, (
                f"роль {role}: простановка отметки должна быть разрешена (право edit), "
                f"получили {resp.status_code}: {resp.text}"
            )
            resp = await client.delete(f"/api/contracts/{target}/labels/prepared", headers=headers)
            assert resp.status_code == 204, (
                f"роль {role}: снятие отметки должно быть разрешено, "
                f"получили {resp.status_code}: {resp.text}"
            )
        else:
            assert resp.status_code == 403, (
                f"роль {role}: простановка отметки должна быть запрещена, "
                f"получили {resp.status_code}: {resp.text}"
            )


# --------------------------------------------------------------------------
# База шаблонов (ТЗ, раздел 6-7)
# --------------------------------------------------------------------------


async def test_template_matrix(client, roster):
    for role, headers in roster.items():
        resp = await client.post(
            "/api/templates",
            json={"name": f"Шаблон роли {role}", "doc_type": "nda", "content": "1. Текст пункта"},
            headers=headers,
        )
        if role in CAN_CREATE:
            assert resp.status_code == 201, (
                f"роль {role}: создание шаблона должно быть разрешено, "
                f"получили {resp.status_code}: {resp.text}"
            )
            template_id = resp.json()["id"]

            verify_resp = await client.post(f"/api/templates/{template_id}/verify", headers=headers)
            if role in VERIFY_TEMPLATE_ALLOWED:
                assert verify_resp.status_code == 200, (
                    f"роль {role}: верификация шаблона должна быть разрешена "
                    f"(ТЗ, раздел 7 — старший юрист/руководитель), "
                    f"получили {verify_resp.status_code}: {verify_resp.text}"
                )
            else:
                assert verify_resp.status_code == 403, (
                    f"роль {role}: верификация шаблона юристу не положена (ТЗ, раздел 7), "
                    f"получили {verify_resp.status_code}"
                )

            archive_resp = await client.delete(f"/api/templates/{template_id}", headers=headers)
            assert archive_resp.status_code == 204, (
                f"роль {role}: архивация собственного шаблона должна быть разрешена, "
                f"получили {archive_resp.status_code}: {archive_resp.text}"
            )
        else:
            assert resp.status_code == 403, (
                f"роль {role}: создание шаблона должно быть запрещено, "
                f"получили {resp.status_code}: {resp.text}"
            )


# --------------------------------------------------------------------------
# Переходы workflow
# --------------------------------------------------------------------------


async def test_workflow_approve_legal_matrix(client, roster):
    """ТЗ, раздел 2: «Подтверждён юристом» ставит юрист — и оба «старших»,
    и администратор, поскольку они «всё, что юрист» (раздел 7)."""
    approve_legal_allowed = CAN_CREATE
    for role, headers in roster.items():
        cid = await _prep_workflow_contract(client, roster, role, "draft")
        resp = await client.post(
            f"/api/contracts/{cid}/workflow/approve_legal", json={}, headers=headers
        )
        if role in approve_legal_allowed:
            assert resp.status_code == 200, (
                f"роль {role}: юридическое подтверждение должно быть разрешено "
                f"(ТЗ, раздел 2), получили {resp.status_code}: {resp.text}"
            )
            assert resp.json()["status"] == "approved"
        else:
            assert resp.status_code == 403, (
                f"роль {role}: юридическое подтверждение должно быть запрещено, "
                f"получили {resp.status_code}: {resp.text}"
            )


async def test_workflow_approve_finance_matrix(client, roster):
    """Финансовое согласование — надстройка сверх ТЗ: право есть только у
    роли «финансы» (и у администратора)."""
    for role, headers in roster.items():
        cid = await _prep_workflow_contract(client, roster, role, "approved")
        resp = await client.post(
            f"/api/contracts/{cid}/workflow/approve_finance", json={}, headers=headers
        )
        if role in APPROVE_FINANCE_ALLOWED:
            assert resp.status_code == 200, (
                f"роль {role}: финансовое согласование должно быть разрешено, "
                f"получили {resp.status_code}: {resp.text}"
            )
            assert resp.json()["status"] == "approved_finance"
        else:
            assert resp.status_code == 403, (
                f"роль {role}: финансовое согласование должно быть запрещено, "
                f"получили {resp.status_code}: {resp.text}"
            )


async def test_workflow_finalize_matrix(client, roster):
    """ТЗ, раздел 7: «Финальный» — «Старший юрист / руководитель», не
    рядовой юрист (см. также test_finalize_is_closed_to_ordinary_lawyer в
    test_legal_engine.py — здесь та же граница проверяется по всей матрице)."""
    for role, headers in roster.items():
        cid = await _prep_workflow_contract(client, roster, role, "approved")
        resp = await client.post(f"/api/contracts/{cid}/workflow/finalize", json={}, headers=headers)
        if role in FINALIZE_ALLOWED:
            assert resp.status_code == 200, (
                f"роль {role}: перевод в «Финальный» должен быть разрешён "
                f"(ТЗ, раздел 7), получили {resp.status_code}: {resp.text}"
            )
            assert resp.json()["status"] == "ready_to_sign"
        else:
            assert resp.status_code == 403, (
                f"роль {role}: перевод в «Финальный» должен быть запрещён, "
                f"получили {resp.status_code}: {resp.text}"
            )


async def test_workflow_reject_matrix(client, roster):
    """workflow.py: возврат на доработку доступен любому, кто способен хоть
    на какое-то согласование — иначе документ, споткнувшийся на финансовом
    шаге, некому вернуть юристу."""
    for role, headers in roster.items():
        cid = await _prep_workflow_contract(client, roster, role, "approved")
        resp = await client.post(
            f"/api/contracts/{cid}/workflow/reject",
            json={"comment": "Вернуть на доработку"},
            headers=headers,
        )
        if role in REJECT_ALLOWED:
            assert resp.status_code == 200, (
                f"роль {role}: возврат на доработку должен быть разрешён, "
                f"получили {resp.status_code}: {resp.text}"
            )
            assert resp.json()["status"] == "needs_revision"
        else:
            assert resp.status_code == 403, (
                f"роль {role}: возврат на доработку должен быть запрещён, "
                f"получили {resp.status_code}: {resp.text}"
            )


async def test_workflow_sign_matrix(client, roster):
    """E-IMZO подписание — надстройка сверх ТЗ. В `ROLE_PERMISSIONS` право
    `sign` буквально есть только у admin: даже руководитель, доведший
    документ до «Финального», сам подписать его через этот эндпоинт не
    может. Фиксируем как текущее поведение (не расхождение с ТЗ — ТЗ
    E-IMZO не описывает), но стоит перепроверить с продуктом осознанно ли
    это ограничение."""
    for role, headers in roster.items():
        cid = await _prep_workflow_contract(client, roster, role, "ready_to_sign")
        resp = await client.post(f"/api/contracts/{cid}/workflow/sign", json={}, headers=headers)
        if role in SIGN_ALLOWED:
            assert resp.status_code == 200, (
                f"роль {role}: подписание (заглушка E-IMZO) должно быть разрешено, "
                f"получили {resp.status_code}: {resp.text}"
            )
            assert resp.json()["status"] == "signed"
        else:
            assert resp.status_code == 403, (
                f"роль {role}: подписание должно быть запрещено, "
                f"получили {resp.status_code}: {resp.text}"
            )


# --------------------------------------------------------------------------
# Управление сотрудниками (ТЗ, раздел 7: право администратора)
# --------------------------------------------------------------------------


async def test_manage_users_matrix(client, roster):
    """ТЗ, раздел 7: «Администратор — управление пользователями». Ни одна
    другая роль в тексте ТЗ такого права не имеет. Роль `head` проверяется
    отдельным xfail-тестом ниже — это известное расхождение, а не пробел
    в этом тесте."""
    for role, headers in roster.items():
        if role == "head":
            continue
        resp = await client.post(
            "/api/users/",
            json={
                "email": f"hired-by-{role}@matrix.uz",
                "username": f"hired-by-{role}",
                "password": "Secret1234",
                "role": "lawyer",
            },
            headers=headers,
        )
        if role == "admin":
            assert resp.status_code == 201, (
                f"роль admin: создание сотрудника должно быть разрешено, "
                f"получили {resp.status_code}: {resp.text}"
            )
        else:
            assert resp.status_code == 403, (
                f"роль {role}: управление сотрудниками — право администратора "
                f"(ТЗ, раздел 7), получили {resp.status_code}: {resp.text}"
            )


async def test_head_manages_staff_as_deliberate_extension(client, admin_headers):
    """Руководитель отдела заводит сотрудников — расширение сверх ТЗ.

    ТЗ (раздел 7) отдаёт «Управление пользователями» строке «Администратор», а
    строке «Старший юрист / руководитель» перечисляет только «Финальный»,
    верификацию шаблонов и доступ ко всем проектам. Формально `manage_users` у
    роли `head` — это шире ТЗ.

    Решено оставить: начальник юротдела, который не может завести нового
    юриста без администратора, — источник ежедневной волокиты, а не защита.
    Расхождение помечено в SPEC_GAP_ANALYSIS.md как осознанное расширение,
    рядом с `approved_finance` и `signed`. У старшего юриста этого права нет:
    расширение точечное, а не «руководству можно всё».
    """
    head = await _make_user(client, admin_headers, "head-matrix@test.uz", "head-matrix", "head")
    resp = await client.post(
        "/api/users/",
        json={
            "email": "hired-by-head@test.uz",
            "username": "hired-by-head",
            "password": "Secret1234",
            "role": "lawyer",
        },
        headers=head,
    )
    assert resp.status_code == 201, resp.text

    senior = await _make_user(
        client, admin_headers, "senior-matrix2@test.uz", "senior-matrix2", "senior_lawyer"
    )
    denied = await client.post(
        "/api/users/",
        json={
            "email": "hired-by-senior@test.uz",
            "username": "hired-by-senior",
            "password": "Secret1234",
            "role": "lawyer",
        },
        headers=senior,
    )
    assert denied.status_code == 403, "расширение точечное: старший юрист сотрудников не заводит"
