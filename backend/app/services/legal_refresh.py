"""Scheduled refresh for imported lex.uz legal sources."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services import legal_search
from app.services.legal_ingest import upsert_legal_document
from app.services.lexuz import fetch_lexuz_html, load_historical_articles, parse_lexuz_html

logger = logging.getLogger("app.legal_refresh")

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "data" / "lexuz_core_sources.json"


def load_legal_sources(manifest_path: str | Path = DEFAULT_MANIFEST) -> list[dict]:
    path = Path(manifest_path)
    if not path.exists():
        logger.warning("legal source manifest not found: %s", path)
        return []
    return json.loads(path.read_text(encoding="utf-8"))


async def refresh_legal_sources(
    db: AsyncSession,
    *,
    sources: list[dict] | None = None,
    cache_dir: str | Path | None = None,
    refresh_html: bool = True,
    delay_seconds: float = 1.0,
) -> tuple[int, int]:
    sources = sources if sources is not None else load_legal_sources()
    documents = 0
    articles = 0
    for index, source in enumerate(sources):
        html = await fetch_lexuz_html(
            source["url"],
            cache_dir=cache_dir or settings.LEXUZ_CACHE_DIR,
            refresh=refresh_html,
        )
        parsed = parse_lexuz_html(
            html,
            url=source["url"],
            title=source.get("title"),
            doc_type=source.get("doc_type"),
            language=source.get("language", "ru"),
            jurisdiction=source.get("jurisdiction", "Uzbekistan"),
            source_id=source.get("source_id"),
            number=source.get("number"),
            adopted_at=source.get("adopted_at"),
            effective_at=source.get("effective_at"),
        )
        if source.get("historical_sources"):
            parsed.metadata["historical_articles"] = await load_historical_articles(
                source["historical_sources"],
                cache_dir=cache_dir or settings.LEXUZ_CACHE_DIR,
                refresh=refresh_html,
            )
        result = await upsert_legal_document(db, parsed)
        await db.commit()
        documents += 1
        articles += result.articles_count
        if delay_seconds > 0 and index < len(sources) - 1:
            await asyncio.sleep(delay_seconds)

    indexed = await legal_search.reindex_all(db)
    logger.info(
        "legal sources refreshed: documents=%s articles=%s indexed=%s",
        documents,
        articles,
        indexed,
    )
    return documents, articles
