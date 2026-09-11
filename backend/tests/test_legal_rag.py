import pytest

from app.agents.law_agent import LawAgent
from app.agents.response_standard import legal_basis_lines
from app.db.models import LegalArticle, LegalDocument
from app.services import legal_search
from app.services.lexuz import parse_lexuz_html
from app.utils import llm


SAMPLE_LEXUZ_HTML = """
<html>
  <head><title>01.01.2026. Test Act</title></head>
  <body>
    <div id="divCont">
      <div class="ACT_TITLE lx_elem"><div class="lx_elem2"></div><div name="1" id="1">Test Act</div></div>
      <div class="CLAUSE_DEFAULT lx_elem"><div class="lx_elem2"></div><div name="10" id="10">Статья 1. Общие правила</div></div>
      <div class="ACT_TEXT lx_elem"><div class="lx_elem2"></div><div name="11" id="11">Договор должен исполняться надлежащим образом.</div></div>
      <div class="CLAUSE_DEFAULT lx_elem"><div class="lx_elem2"></div><div name="20" id="20">Статья 2. Ответственность</div></div>
      <div class="ACT_TEXT lx_elem"><div class="lx_elem2"></div><div name="21" id="21">Стороны несут ответственность за просрочку оплаты.</div></div>
    </div>
  </body>
</html>
"""


def test_parse_lexuz_html_splits_articles():
    parsed = parse_lexuz_html(
        SAMPLE_LEXUZ_HTML,
        url="https://lex.uz/ru/docs/999",
        title="Test Act",
        doc_type="law",
    )

    assert parsed.source_id == "999"
    assert len(parsed.articles) == 2
    assert parsed.articles[0].article_number == "1"
    assert parsed.articles[0].url == "https://lex.uz/ru/docs/999#10"
    assert "надлежащим образом" in parsed.articles[0].content


def test_parse_lexuz_html_preserves_superscript_article_number():
    html = SAMPLE_LEXUZ_HTML.replace(
        "Статья 2. Ответственность",
        "Статья 66<sup>1</sup>. Освобождение от ответственности",
    )
    parsed = parse_lexuz_html(
        html,
        url="https://lex.uz/ru/docs/999",
        title="Test Act",
        doc_type="code",
    )

    assert parsed.articles[1].article_number == "66-1"
    assert parsed.articles[1].title.startswith("Статья 66-1.")


async def _seed_law(session):
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
    session.add(
        LegalArticle(
            document_id=document.id,
            source_article_id="10977",
            article_number="21",
            title="Статья 21. Правовая экспертиза хозяйственных договоров",
            content=(
                "Статья 21. Правовая экспертиза хозяйственных договоров\n"
                "Хозяйственные договоры должны быть проверены юридической службой."
            ),
            content_hash="hash",
            position=1,
            url="https://lex.uz/ru/docs/10872#10977",
        )
    )
    await session.commit()


async def _seed_criminal_code(session):
    document = LegalDocument(
        source="lex.uz",
        source_id="111457",
        language="ru",
        jurisdiction="Uzbekistan",
        doc_type="code",
        title="Уголовный кодекс Республики Узбекистан",
        url="https://lex.uz/ru/docs/111457",
        status="active",
    )
    session.add(document)
    await session.flush()
    session.add_all(
        [
            LegalArticle(
                document_id=document.id,
                source_article_id="1723524",
                article_number="66",
                title=(
                    "Статья 66. Освобождение от ответственности в связи с "
                    "деятельным раскаянием виновного в содеянном"
                ),
                content=(
                    "Статья 66. Освобождение от ответственности в связи с "
                    "деятельным раскаянием виновного в содеянном. Лицо, впервые "
                    "совершившее преступление, может быть освобождено от ответственности."
                ),
                content_hash="criminal-66",
                position=66,
                url="https://lex.uz/ru/docs/111457#1723524",
            ),
            LegalArticle(
                document_id=document.id,
                source_article_id="1723525",
                article_number="67",
                title="Статья 67. Освобождение от ответственности",
                content="Статья 67. Другая норма уголовного закона.",
                content_hash="criminal-67",
                position=67,
                url="https://lex.uz/ru/docs/111457#1723525",
            ),
        ]
    )
    await session.commit()


async def _seed_civil_code_with_repealed_article(session):
    document = LegalDocument(
        source="lex.uz",
        source_id="111181",
        language="ru",
        jurisdiction="Uzbekistan",
        doc_type="code",
        title="Гражданский кодекс Республики Узбекистан (часть первая)",
        url="https://lex.uz/ru/docs/111181",
        status="active",
        extra_data={
            "historical_articles": [
                {
                    "article_number": "66",
                    "article_title": "Статья 66. Закрытое акционерное общество",
                    "content": (
                        "Статья 66. Закрытое акционерное общество. "
                        "Акции такого общества распределялись среди учредителей."
                    ),
                    "url": (
                        "https://lex.uz/ru/docs/111181?"
                        "ONDATE=01.03.1997%2000#156804"
                    ),
                    "reference_status": "repealed",
                    "repealed_at": "2014-05-15",
                    "repeal_notice": (
                        "Статьи 65 и 66 утратили силу в соответствии с Законом "
                        "Республики Узбекистан от 14 мая 2014 года № ЗРУ-372."
                    ),
                    "repeal_law_url": "https://lex.uz/ru/docs/2388209",
                    "historical_revision_date": "1997-03-01",
                }
            ]
        },
    )
    session.add(document)
    await session.flush()
    session.add(
        LegalArticle(
            document_id=document.id,
            source_article_id="156795",
            article_number="64",
            title="Статья 64. Акционерное общество",
            content="Статья 64. Акционерное общество. Действующая норма.",
            content_hash="civil-64",
            position=64,
            url="https://lex.uz/ru/docs/111181#156795",
        )
    )
    await session.commit()


async def _seed_uzbek_codes_with_foreign_lookalike_numbers(session):
    """ГК/ТК/УК Республики Узбекистан со статьями тех же номеров, что часто
    встречаются в запросах к иностранным кодексам (ст. 330 ГК РФ, ст. 57 ТК
    РФ, ст. 105 УК РФ) — чтобы отличить совпадение номера статьи от совпадения
    юрисдикции (D1, docs/SVOD_PROTOTYPE_DELTA.md, раздел 3)."""
    civil = LegalDocument(
        source="lex.uz",
        source_id="civil-330",
        language="ru",
        jurisdiction="Uzbekistan",
        doc_type="code",
        title="Гражданский кодекс Республики Узбекистан (часть первая)",
        url="https://lex.uz/ru/docs/civil-330",
        status="active",
    )
    session.add(civil)
    await session.flush()
    session.add(
        LegalArticle(
            document_id=civil.id,
            source_article_id="civil-330-art",
            article_number="330",
            title="Статья 330. Понятие неустойки",
            content=(
                "Статья 330. Неустойкой признаётся определённая законом или "
                "договором денежная сумма, которую должник обязан уплатить "
                "кредитору в случае неисполнения обязательства."
            ),
            content_hash="civil-330",
            position=330,
            url="https://lex.uz/ru/docs/civil-330#art",
        )
    )

    labor = LegalDocument(
        source="lex.uz",
        source_id="labor-57",
        language="ru",
        jurisdiction="Uzbekistan",
        doc_type="code",
        title="Трудовой кодекс Республики Узбекистан",
        url="https://lex.uz/ru/docs/labor-57",
        status="active",
    )
    session.add(labor)
    await session.flush()
    session.add(
        LegalArticle(
            document_id=labor.id,
            source_article_id="labor-57-art",
            article_number="57",
            title="Статья 57. Срочный трудовой договор",
            content=(
                "Статья 57. Срочный трудовой договор заключается в случаях, "
                "когда трудовые отношения не могут быть установлены на "
                "неопределённый срок."
            ),
            content_hash="labor-57",
            position=57,
            url="https://lex.uz/ru/docs/labor-57#art",
        )
    )

    criminal = LegalDocument(
        source="lex.uz",
        source_id="criminal-105",
        language="ru",
        jurisdiction="Uzbekistan",
        doc_type="code",
        title="Уголовный кодекс Республики Узбекистан",
        url="https://lex.uz/ru/docs/criminal-105",
        status="active",
    )
    session.add(criminal)
    await session.flush()
    session.add(
        LegalArticle(
            document_id=criminal.id,
            source_article_id="criminal-105-art",
            article_number="105",
            title="Статья 105. Умышленное причинение тяжкого телесного повреждения",
            content=(
                "Статья 105. Умышленное причинение тяжкого телесного "
                "повреждения наказывается лишением свободы."
            ),
            content_hash="criminal-105",
            position=105,
            url="https://lex.uz/ru/docs/criminal-105#art",
        )
    )
    await session.commit()


@pytest.fixture(autouse=True)
def no_legal_elasticsearch(monkeypatch):
    async def unavailable(**kwargs):
        raise ConnectionError("ES down in tests")

    monkeypatch.setattr(legal_search, "_search_es", unavailable)


async def test_legal_search_sql_fallback(db_factory):
    async with db_factory() as session:
        await _seed_law(session)
        results = await legal_search.search_legal_articles(
            session,
            q="правовая экспертиза хозяйственного договора",
            limit=5,
        )

    assert len(results) == 1
    assert results[0]["engine"] == "sql"
    assert results[0]["article_number"] == "21"
    assert "lex.uz/ru/docs/10872#10977" in results[0]["url"]


@pytest.mark.parametrize(
    "query",
    [
        "о чем гласит 66 статья УКРУз?",
        "Что предусматривает ст. 66 УК РУз?",
        "Покажи статью 66 Уголовного кодекса Республики Узбекистан",
    ],
)
async def test_legal_search_resolves_exact_code_article(db_factory, query):
    async with db_factory() as session:
        await _seed_criminal_code(session)
        results = await legal_search.search_legal_articles(session, q=query, limit=8)

    assert len(results) == 1
    assert results[0]["engine"] == "sql_exact"
    assert results[0]["document_title"] == "Уголовный кодекс Республики Узбекистан"
    assert results[0]["article_number"] == "66"
    assert results[0]["url"] == "https://lex.uz/ru/docs/111457#1723524"


async def test_exact_repealed_article_returns_historical_edition(db_factory):
    async with db_factory() as session:
        await _seed_civil_code_with_repealed_article(session)
        await _seed_criminal_code(session)
        results = await legal_search.search_legal_articles(
            session,
            q="А 66 статья Гражданского кодекса?",
            limit=8,
        )

    assert len(results) == 1
    assert results[0]["engine"] == "sql_exact_historical"
    assert results[0]["reference_status"] == "repealed"
    assert results[0]["document_title"].startswith("Гражданский кодекс")
    assert "Закрытое акционерное общество" in results[0]["content"]
    assert "Уголовный кодекс" not in results[0]["document_title"]

    basis = legal_basis_lines(results)
    assert basis[0].startswith("Историческая редакция:")
    assert "не является действующим правовым основанием" in basis[0]
    assert "ЗРУ-372" in basis[0]
    assert "https://lex.uz/ru/docs/2388209" in basis[0]


async def test_missing_exact_article_does_not_fall_back_to_another_act(db_factory):
    async with db_factory() as session:
        await _seed_criminal_code(session)
        results = await legal_search.search_legal_articles(
            session,
            q="Статья 66 Гражданского кодекса",
            limit=8,
        )

    assert results == []


@pytest.mark.parametrize(
    "query",
    [
        "ст. 330 ГК РФ",
        "ст. 57 ТК РФ",
        "ст. 105 УК РФ",
        "ст. 330 ГК Казахстана",
    ],
)
async def test_foreign_jurisdiction_reference_does_not_resolve_to_uzbek_act(
    db_factory, query
):
    """D1: маркер чужой юрисдикции (РФ, Казахстана) сейчас игнорируется —
    ACT_REFERENCE_PATTERNS резолвит запрос в узбекский кодекс с тем же
    номером статьи (legal_search.py:83, необязательная группа
    `(?:руз|республики\\s+узбекистан)?`). Юрист получает чужую норму под
    видом запрошенной. Пустой результат — приемлемо, подмена акта — нет."""
    async with db_factory() as session:
        await _seed_uzbek_codes_with_foreign_lookalike_numbers(session)
        results = await legal_search.search_legal_articles(session, q=query, limit=8)

    assert results == []


@pytest.mark.parametrize(
    "query,expected_article_number",
    [
        ("ст. 330 ГК РУз", "330"),
        ("ст. 57 ТК РУз", "57"),
        ("ст. 105 УК РУз", "105"),
        ("Статья 330 Гражданского кодекса Республики Узбекистан", "330"),
    ],
)
async def test_uzbek_jurisdiction_reference_still_resolves(
    db_factory, query, expected_article_number
):
    """Контроль к D1: фикс не должен сломать основной сценарий — запрос с
    явно узбекской юрисдикцией (или без указания юрисдикции вовсе) обязан
    по-прежнему находить узбекскую норму."""
    async with db_factory() as session:
        await _seed_uzbek_codes_with_foreign_lookalike_numbers(session)
        results = await legal_search.search_legal_articles(session, q=query, limit=8)

    assert len(results) == 1
    assert results[0]["engine"] == "sql_exact"
    assert results[0]["article_number"] == expected_article_number
    assert "Республики Узбекистан" in results[0]["document_title"]


async def test_law_agent_uses_local_lexuz_context(db_factory, monkeypatch):
    async with db_factory() as session:
        await _seed_law(session)

        async def fake_llm_json(*, system: str, user: str, max_tokens: int = 4000) -> dict:
            assert "Нормы из локальной базы lex.uz" in user
            assert "Статья 21. Правовая экспертиза" in user
            return {
                "legal_issues": [],
                "compliance_status": "compliant",
                "recommendations": [],
            }

        monkeypatch.setattr(llm, "llm_json", fake_llm_json)

        result = await LawAgent().check_legislation(
            "Нужна правовая экспертиза хозяйственного договора.",
            db=session,
        )

    assert result["source"] == "local_lexuz_rag"
    assert result["legal_sources"][0]["article_number"] == "21"
    assert result["legal_basis"][0]["url"] == "https://lex.uz/ru/docs/10872#10977"
    assert "Правовое основание:" in result["legal_basis"][0]["text"]
    assert "Примечание юриста:" in result["lawyer_note"]
