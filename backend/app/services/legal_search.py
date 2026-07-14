"""Search and formatting helpers for legal-act RAG."""

from __future__ import annotations

import html
import logging
import re
from collections import Counter
from datetime import date
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import LegalArticle, LegalDocument
from app.services.search import get_client

logger = logging.getLogger("app.legal_search")

INDEX = "legal_articles"

MAPPING = {
    "settings": {
        "analysis": {
            "analyzer": {
                "ru": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "russian_morphology_stub"],
                }
            },
            "filter": {
                "russian_morphology_stub": {"type": "stemmer", "language": "russian"}
            },
        }
    },
    "mappings": {
        "properties": {
            "source": {"type": "keyword"},
            "source_id": {"type": "keyword"},
            "document_id": {"type": "keyword"},
            "document_title": {"type": "text", "analyzer": "ru"},
            "document_number": {"type": "keyword"},
            "doc_type": {"type": "keyword"},
            "language": {"type": "keyword"},
            "status": {"type": "keyword"},
            "article_number": {"type": "keyword"},
            "article_title": {"type": "text", "analyzer": "ru"},
            "content": {"type": "text", "analyzer": "ru"},
            "url": {"type": "keyword"},
            "current_revision_date": {"type": "date"},
            "position": {"type": "integer"},
        }
    },
}

STOPWORDS = {
    "договор",
    "договора",
    "договоре",
    "сторона",
    "стороны",
    "который",
    "которая",
    "которые",
    "настоящий",
    "настоящего",
    "республики",
    "узбекистан",
    "условия",
    "может",
    "должен",
    "должна",
    "есть",
    "если",
    "или",
    "для",
    "при",
    "что",
}

ACT_REFERENCE_PATTERNS = (
    (
        re.compile(
            r"\b(?:ук\s*(?:руз|республики\s+узбекистан)?|"
            r"уголовн\w*\s+кодекс\w*)\b",
            re.IGNORECASE,
        ),
        "Уголовный кодекс",
    ),
    (
        re.compile(
            r"\b(?:гк\s*(?:руз|республики\s+узбекистан)?|"
            r"гражданск\w*\s+кодекс\w*)\b",
            re.IGNORECASE,
        ),
        "Гражданский кодекс",
    ),
    (
        re.compile(
            r"\b(?:тк\s*(?:руз|республики\s+узбекистан)?|"
            r"трудов\w*\s+кодекс\w*)\b",
            re.IGNORECASE,
        ),
        "Трудовой кодекс",
    ),
    (
        re.compile(
            r"\b(?:нк\s*(?:руз|республики\s+узбекистан)?|"
            r"налогов\w*\s+кодекс\w*)\b",
            re.IGNORECASE,
        ),
        "Налоговый кодекс",
    ),
)

ARTICLE_REFERENCE_PATTERNS = (
    re.compile(r"(?:стать\w*|ст\.)\s*№?\s*(\d+(?:[-–—]\d+)?)", re.IGNORECASE),
    re.compile(r"\b(\d+(?:[-–—]\d+)?)\s+(?:стать\w*|ст\.)", re.IGNORECASE),
)


async def ensure_index() -> bool:
    try:
        client = get_client()
        if not await client.indices.exists(index=INDEX):
            await client.indices.create(index=INDEX, **MAPPING)
            logger.info("legal search index created")
        return True
    except Exception:
        logger.warning("elasticsearch unavailable, legal search runs on SQL fallback")
        return False


async def index_legal_article(article: LegalArticle) -> None:
    try:
        await get_client().index(
            index=INDEX,
            id=str(article.id),
            document=_doc(article),
        )
    except Exception:
        logger.debug("skip legal article indexing: elasticsearch unavailable")


async def delete_legal_article(article_id) -> None:
    try:
        await get_client().delete(index=INDEX, id=str(article_id), ignore=[404])
    except Exception:
        logger.debug("skip legal article delete: elasticsearch unavailable")


async def search_legal_articles(
    db: AsyncSession,
    *,
    q: str,
    limit: int = 8,
    language: str = "ru",
    source_ids: list[str] | None = None,
    doc_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    q = (q or "").strip()
    if not q:
        return []

    reference = _parse_legal_reference(q)
    if reference:
        exact = await _search_exact_reference(
            db,
            document_title=reference[0],
            article_number=reference[1],
            language=language,
            source_ids=source_ids,
            doc_types=doc_types,
        )
        if exact:
            return exact[:limit]

    try:
        results = await _search_es(
            q=q,
            limit=limit,
            language=language,
            source_ids=source_ids,
            doc_types=doc_types,
        )
        if results:
            return results
    except Exception:
        pass
    return await _search_sql(
        db,
        q=q,
        limit=limit,
        language=language,
        source_ids=source_ids,
        doc_types=doc_types,
    )


async def _search_exact_reference(
    db: AsyncSession,
    *,
    document_title: str,
    article_number: str,
    language: str,
    source_ids: list[str] | None,
    doc_types: list[str] | None,
) -> list[dict[str, Any]]:
    query = (
        select(LegalArticle)
        .options(selectinload(LegalArticle.document))
        .join(LegalArticle.document)
        .where(
            LegalDocument.language == language,
            LegalDocument.status == "active",
            LegalDocument.title.ilike(f"%{document_title}%"),
            LegalArticle.article_number == article_number,
        )
        .order_by(LegalArticle.position)
    )
    if source_ids:
        query = query.where(LegalDocument.source_id.in_(source_ids))
    if doc_types:
        query = query.where(LegalDocument.doc_type.in_(doc_types))

    articles = (await db.execute(query)).scalars().unique()
    results = [_serialize_sql(article, [f"статья {article_number}"]) for article in articles]
    for result in results:
        result["engine"] = "sql_exact"
    return results


async def reindex_all(db: AsyncSession) -> int:
    # Индекс пересоздаём с нуля: upsert документа удаляет старые строки из БД,
    # но их ES-записи иначе остаются призраками и дублируют выдачу агентам
    try:
        await get_client().indices.delete(index=INDEX, ignore=[404])
    except Exception:
        logger.warning("elasticsearch unavailable, skip reindex")
        return 0
    if not await ensure_index():
        return 0
    rows = (
        await db.execute(
            select(LegalArticle)
            .options(selectinload(LegalArticle.document))
            .join(LegalArticle.document)
            .where(LegalDocument.status == "active")
            .order_by(LegalDocument.source_id, LegalArticle.position)
        )
    ).scalars()
    count = 0
    for article in rows:
        await index_legal_article(article)
        count += 1
    return count


def format_legal_context(
    sources: list[dict[str, Any]],
    *,
    max_chars: int = 12_000,
) -> str:
    if not sources:
        return ""
    blocks: list[str] = []
    used = 0
    for index, source in enumerate(sources, start=1):
        revision = source.get("current_revision_date") or "unknown revision"
        header = (
            f"[L{index}] {source['document_title']} - "
            f"{source.get('article_title') or source.get('article_number') or 'fragment'} "
            f"(редакция: {revision})\n{source['url']}"
        )
        content = _clip(source["content"], 1600)
        block = f"{header}\n{content}"
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)


def build_contract_law_query(contract_content: str, errors: list | None = None) -> str:
    base = contract_content[:2500]
    structural_errors = ""
    if errors:
        structural_errors = " ".join(
            str(item.get("description") or item.get("issue") or item)
            for item in errors[:8]
            if item
        )
    return (
        f"{base}\n{structural_errors}\n"
        "договор обязательство исполнение срок оплата ответственность неустойка "
        "расторжение изменение форма договора существенные условия претензия спор "
        "хозяйственный договор правовая экспертиза"
    )


def _doc(article: LegalArticle) -> dict[str, Any]:
    document = article.document
    return {
        "source": document.source,
        "source_id": document.source_id,
        "document_id": str(document.id),
        "document_title": document.title,
        "doc_type": document.doc_type,
        "language": document.language,
        "status": document.status,
        "article_number": article.article_number,
        "article_title": article.title,
        "content": article.content,
            "url": article.url,
            "document_number": document.number,
            "adopted_at": _date_iso(document.adopted_at),
            "current_revision_date": _date_iso(document.current_revision_date),
        "position": article.position,
    }


async def _search_es(
    *,
    q: str,
    limit: int,
    language: str,
    source_ids: list[str] | None,
    doc_types: list[str] | None,
) -> list[dict[str, Any]]:
    filters: list[dict] = [
        {"term": {"language": language}},
        {"term": {"status": "active"}},
    ]
    if source_ids:
        filters.append({"terms": {"source_id": source_ids}})
    if doc_types:
        filters.append({"terms": {"doc_type": doc_types}})

    response = await get_client().search(
        index=INDEX,
        query={
            "bool": {
                "must": {
                    "multi_match": {
                        "query": q,
                        "fields": [
                            "article_title^4",
                            "document_title^3",
                            "content",
                        ],
                        "operator": "or",
                        "fuzziness": "AUTO",
                    }
                },
                "filter": filters,
            }
        },
        highlight={
            "encoder": "html",
            "fields": {
                "content": {
                    "fragment_size": 220,
                    "number_of_fragments": 2,
                    "pre_tags": ["<mark>"],
                    "post_tags": ["</mark>"],
                }
            },
        },
        size=limit,
    )
    results: list[dict[str, Any]] = []
    for hit in response["hits"]["hits"]:
        source = hit["_source"]
        results.append(
            {
                **source,
                "id": hit["_id"],
                "score": hit.get("_score"),
                "snippets": hit.get("highlight", {}).get("content", []),
                "engine": "elasticsearch",
            }
        )
    return results


async def _search_sql(
    db: AsyncSession,
    *,
    q: str,
    limit: int,
    language: str,
    source_ids: list[str] | None,
    doc_types: list[str] | None,
) -> list[dict[str, Any]]:
    terms = _query_terms(q)
    if not terms:
        return []

    conditions = []
    for term in terms:
        pattern = f"%{term}%"
        conditions.extend(
            [
                LegalArticle.content.ilike(pattern),
                LegalArticle.title.ilike(pattern),
                LegalDocument.title.ilike(pattern),
            ]
        )

    query = (
        select(LegalArticle)
        .options(selectinload(LegalArticle.document))
        .join(LegalArticle.document)
        .where(
            LegalDocument.language == language,
            LegalDocument.status == "active",
            or_(*conditions),
        )
    )
    if source_ids:
        query = query.where(LegalDocument.source_id.in_(source_ids))
    if doc_types:
        query = query.where(LegalDocument.doc_type.in_(doc_types))

    candidates = (
        await db.execute(query.order_by(LegalArticle.position).limit(max(limit * 6, 30)))
    ).scalars()
    ranked = sorted(
        candidates,
        key=lambda article: _sql_score(article, terms),
        reverse=True,
    )
    return [_serialize_sql(article, terms) for article in ranked[:limit]]


def _serialize_sql(article: LegalArticle, terms: list[str]) -> dict[str, Any]:
    document = article.document
    return {
        "id": str(article.id),
        "source": document.source,
        "source_id": document.source_id,
        "document_id": str(document.id),
        "document_title": document.title,
        "doc_type": document.doc_type,
        "language": document.language,
        "status": document.status,
        "article_number": article.article_number,
        "article_title": article.title,
        "content": article.content,
        "url": article.url,
        "document_number": document.number,
        "adopted_at": _date_iso(document.adopted_at),
        "current_revision_date": _date_iso(document.current_revision_date),
        "position": article.position,
        "score": _sql_score(article, terms),
        "snippets": [_sql_snippet(article.content, terms)],
        "engine": "sql",
    }


def _query_terms(q: str) -> list[str]:
    raw_terms = re.findall(r"[A-Za-zА-Яа-яЁёЎўҚқҒғҲҳ0-9]{4,}", q.lower())
    counts = Counter(term for term in raw_terms if term not in STOPWORDS)
    return [term for term, _ in counts.most_common(12)]


def _parse_legal_reference(q: str) -> tuple[str, str] | None:
    document_title = next(
        (title for pattern, title in ACT_REFERENCE_PATTERNS if pattern.search(q)),
        None,
    )
    if document_title is None:
        return None

    for pattern in ARTICLE_REFERENCE_PATTERNS:
        match = pattern.search(q)
        if match:
            article_number = re.sub(r"[-–—]", "-", match.group(1))
            return document_title, article_number
    return None


def _sql_score(article: LegalArticle, terms: list[str]) -> int:
    haystack = f"{article.title or ''}\n{article.document.title}\n{article.content}".lower()
    return sum(haystack.count(term.lower()) for term in terms)


def _sql_snippet(content: str, terms: list[str]) -> str:
    lower = content.lower()
    positions = [
        lower.find(term.lower())
        for term in terms
        if lower.find(term.lower()) >= 0
    ]
    if not positions:
        return html.escape(_clip(content, 220))
    pos = min(positions)
    start = max(pos - 100, 0)
    end = min(pos + 180, len(content))
    snippet = content[start:end]
    escaped = html.escape(("..." if start else "") + snippet + ("..." if end < len(content) else ""))
    for term in terms:
        escaped = re.sub(
            re.escape(html.escape(term)),
            lambda m: f"<mark>{m.group(0)}</mark>",
            escaped,
            flags=re.IGNORECASE,
        )
    return escaped


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


def _date_iso(value: date | None) -> str | None:
    return value.isoformat() if value else None
