"""Import public lex.uz acts into the local legal knowledge base.

Run from backend:
    python -m scripts.ingest_lexuz
    python -m scripts.ingest_lexuz --url https://lex.uz/ru/docs/10872
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.db.base import async_session_factory
from app.services import legal_search
from app.services.legal_ingest import upsert_legal_document
from app.services.lexuz import fetch_lexuz_html, parse_lexuz_html
from app.services.search import get_client

DEFAULT_MANIFEST = (
    Path(__file__).resolve().parents[1] / "app" / "data" / "lexuz_core_sources.json"
)
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "lexuz"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import lex.uz acts for Law Agent RAG")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--url", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--skip-index", action="store_true")
    return parser.parse_args()


def load_sources(args: argparse.Namespace) -> list[dict]:
    sources: list[dict] = []
    manifest_path = Path(args.manifest)
    if manifest_path.exists():
        sources.extend(json.loads(manifest_path.read_text(encoding="utf-8")))
    for url in args.url:
        sources.append({"url": url, "language": "ru", "doc_type": "law"})
    if args.limit:
        sources = sources[: args.limit]
    return sources


async def ingest_source(session, source: dict, args: argparse.Namespace) -> tuple[str, int]:
    url = source["url"]
    html = await fetch_lexuz_html(
        url,
        cache_dir=args.cache_dir,
        refresh=args.refresh,
    )
    parsed = parse_lexuz_html(
        html,
        url=url,
        title=source.get("title"),
        doc_type=source.get("doc_type"),
        language=source.get("language", "ru"),
        jurisdiction=source.get("jurisdiction", "Uzbekistan"),
        source_id=source.get("source_id"),
        number=source.get("number"),
        adopted_at=source.get("adopted_at"),
        effective_at=source.get("effective_at"),
    )
    result = await upsert_legal_document(session, parsed)
    await session.commit()
    action = "created" if result.created else "updated"
    print(f"{action}: {parsed.title} ({result.articles_count} articles)")
    return parsed.title, result.articles_count


async def main() -> None:
    args = parse_args()
    sources = load_sources(args)
    if not sources:
        print("No sources to import")
        return

    total_articles = 0
    try:
        async with async_session_factory() as session:
            for index, source in enumerate(sources):
                _, count = await ingest_source(session, source, args)
                total_articles += count
                if args.delay > 0 and index < len(sources) - 1:
                    await asyncio.sleep(args.delay)

            if args.skip_index:
                print(f"Imported {len(sources)} documents, {total_articles} articles")
                return

            indexed = await legal_search.reindex_all(session)
            print(
                f"Imported {len(sources)} documents, {total_articles} articles; "
                f"indexed {indexed} articles"
            )
    finally:
        try:
            await get_client().close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
