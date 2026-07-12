"""Law Agent: checks contracts against Uzbekistan legislation using local RAG."""

from __future__ import annotations

import json
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.response_standard import (
    DEFAULT_LAWYER_NOTE,
    LEGAL_RESPONSE_STANDARD,
    NO_DIRECT_LEXUZ_REGULATION,
    legal_basis_payload,
)
from app.db.base import async_session_factory
from app.services.legal_search import (
    build_contract_law_query,
    format_legal_context,
    search_legal_articles,
)
from app.utils import llm

SYSTEM = """Ты — эксперт по законодательству Республики Узбекистан
(Гражданский кодекс, Трудовой кодекс, Налоговый кодекс, закон «О договорно-
правовой базе деятельности хозяйствующих субъектов»).
Проверяешь договор на соответствие законодательству РУз.

Если в запросе передан блок «Нормы из локальной базы lex.uz», опирайся прежде
всего на него. Не выдумывай номера статей: если нормы нет в источниках, честно
укажи, что требуется дополнительная проверка первоисточника.
""" + f"\n\n{LEGAL_RESPONSE_STANDARD}\n\n" + """

Формат ответа — JSON:
{
  "legal_issues": [
    {"issue": "описание проблемы",
     "applicable_law": "название НПА",
     "article": "статья",
     "source_id": "идентификатор L1/L2 из переданного контекста",
     "source_url": "ссылка на lex.uz, если есть",
     "violation_type": "conflict|missing|unclear",
     "recommendation": "как привести в соответствие"}
  ],
  "compliance_status": "compliant|partial|non-compliant",
  "recommendations": ["общая рекомендация", ...],
  "legal_basis": [
    {"text": "Правовое основание: ...", "url": "https://lex.uz/..."}
  ],
  "lawyer_note": "Примечание юриста: ..."
}"""


class LawAgent:
    name = "law_agent"

    def __init__(self, lex_uz_api_key: str | None = None):
        # Kept for backward compatibility with the orchestrator signature. Public
        # lex.uz HTML import does not require a key.
        self.lex_uz_api_key = lex_uz_api_key

    async def check_legislation(
        self,
        contract_content: str,
        errors: list | None = None,
        db: AsyncSession | None = None,
    ) -> dict:
        laws = await self._fetch_relevant_laws(contract_content, errors, db)
        laws_block = (
            "\n\nНормы из локальной базы lex.uz:\n"
            f"{format_legal_context(laws, max_chars=12_000)}"
            if laws
            else ""
        )
        errors_block = (
            "\n\nУже найденные структурные ошибки:\n"
            f"{json.dumps(errors, ensure_ascii=False)[:4000]}"
            if errors
            else ""
        )
        result = await llm.llm_json(
            system=SYSTEM,
            user=(
                "Проверь договор на соответствие законодательству РУз:"
                f"\n\n{llm.clip(contract_content)}{errors_block}{laws_block}"
            ),
        )
        result = _enforce_source_policy(result, laws)
        result["source"] = "local_lexuz_rag" if laws else "model_knowledge"
        result["legal_sources"] = _public_sources(laws)
        return result

    async def _fetch_relevant_laws(
        self,
        content: str,
        errors: list | None,
        db: AsyncSession | None,
    ) -> list[dict]:
        query = build_contract_law_query(content, errors)
        if db is not None:
            return await search_legal_articles(db, q=query, limit=10)

        async with async_session_factory() as session:
            return await search_legal_articles(session, q=query, limit=10)


def _public_sources(sources: list[dict]) -> list[dict]:
    return [
        {
            "document_title": source["document_title"],
            "article_number": source.get("article_number"),
            "article_title": source.get("article_title"),
            "url": source["url"],
            "document_number": source.get("document_number"),
            "adopted_at": source.get("adopted_at"),
            "current_revision_date": source.get("current_revision_date"),
            "status": source.get("status"),
        }
        for source in sources
    ]


def _enforce_source_policy(result: dict, sources: list[dict]) -> dict:
    """Keep Law Agent answers visibly grounded in lex.uz sources."""
    result = dict(result)
    issues = result.get("legal_issues")
    if not isinstance(issues, list):
        issues = []
        result["legal_issues"] = issues

    recommendations = result.get("recommendations")
    if not isinstance(recommendations, list):
        recommendations = []

    if sources:
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            source = _verified_issue_source(issue, sources)
            if source is None:
                issue["source_url"] = None
                issue["article"] = None
                issue["citation_verified"] = False
                continue
            issue["source_url"] = source.get("url")
            issue["applicable_law"] = source.get("document_title")
            issue["article"] = (
                f"статья {source['article_number']}"
                if source.get("article_number")
                else None
            )
            issue["citation_verified"] = True
        result["grounded"] = True
        result["legal_basis"] = legal_basis_payload(sources)
    else:
        warning = NO_DIRECT_LEXUZ_REGULATION
        result["grounded"] = False
        result["source_warning"] = warning
        result["legal_basis"] = []
        recommendations = [warning, *recommendations]
        for issue in issues:
            if isinstance(issue, dict):
                issue.setdefault("source_url", None)

    result["recommendations"] = list(dict.fromkeys(recommendations))
    if "lawyer_note" not in result or not result["lawyer_note"]:
        result["lawyer_note"] = DEFAULT_LAWYER_NOTE
    return result


def _verified_issue_source(issue: dict, sources: list[dict]) -> dict | None:
    source_ref = str(issue.get("source_id") or "").strip().upper()
    if source_ref.startswith("L") and source_ref[1:].isdigit():
        index = int(source_ref[1:]) - 1
        if 0 <= index < len(sources):
            return sources[index]

    claimed_url = str(issue.get("source_url") or "").rstrip(".,; ")
    if claimed_url:
        for source in sources:
            if str(source.get("url") or "").rstrip(".,; ") == claimed_url:
                return source

    article = str(issue.get("article") or "")
    number_match = re.search(r"\d+[0-9A-Za-zА-Яа-яЁёЎўҚқҒғҲҳ/-]*", article)
    if number_match:
        matches = [
            source
            for source in sources
            if str(source.get("article_number") or "") == number_match.group(0)
        ]
        if len(matches) == 1:
            return matches[0]
    return None
