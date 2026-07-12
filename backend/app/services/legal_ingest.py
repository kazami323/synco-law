"""Persistence helpers for the legal knowledge base."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LegalArticle, LegalDocument
from app.services.lexuz import ParsedLegalDocument


@dataclass(frozen=True)
class IngestResult:
    document: LegalDocument
    articles_count: int
    created: bool


async def upsert_legal_document(
    db: AsyncSession, parsed: ParsedLegalDocument
) -> IngestResult:
    existing = (
        await db.execute(
            select(LegalDocument).where(
                LegalDocument.source == parsed.source,
                LegalDocument.source_id == parsed.source_id,
                LegalDocument.language == parsed.language,
            )
        )
    ).scalar_one_or_none()

    created = existing is None
    document = existing or LegalDocument(
        source=parsed.source,
        source_id=parsed.source_id,
        language=parsed.language,
        title=parsed.title,
        url=parsed.url,
    )
    if created:
        db.add(document)

    document.jurisdiction = parsed.jurisdiction
    document.doc_type = parsed.doc_type
    document.title = parsed.title
    document.number = parsed.number
    document.url = parsed.url
    document.adopted_at = parsed.adopted_at
    document.effective_at = parsed.effective_at
    document.current_revision_date = parsed.current_revision_date
    document.status = "active"
    document.extra_data = parsed.metadata
    document.fetched_at = parsed.fetched_at
    await db.flush()

    if not created:
        await db.execute(delete(LegalArticle).where(LegalArticle.document_id == document.id))

    for article in parsed.articles:
        content_hash = hashlib.sha256(article.content.encode("utf-8")).hexdigest()
        db.add(
            LegalArticle(
                document_id=document.id,
                source_article_id=article.source_article_id
                or f"article-{article.position}",
                article_number=article.article_number,
                title=article.title,
                content=article.content,
                content_hash=content_hash,
                position=article.position,
                url=article.url,
                extra_data={"source": parsed.source, "source_id": parsed.source_id},
            )
        )

    await db.flush()
    return IngestResult(
        document=document,
        articles_count=len(parsed.articles),
        created=created,
    )
