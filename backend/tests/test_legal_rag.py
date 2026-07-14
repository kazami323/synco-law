import pytest

from app.agents.law_agent import LawAgent
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
