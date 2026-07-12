"""Rebuild Elasticsearch index for imported legal articles.

Run from backend:
    python -m scripts.reindex_laws
"""

from __future__ import annotations

import asyncio

from app.db.base import async_session_factory
from app.services.legal_search import reindex_all
from app.services.search import get_client


async def main() -> None:
    try:
        async with async_session_factory() as session:
            count = await reindex_all(session)
            if count:
                print(f"Indexed legal articles: {count}")
            else:
                print("Elasticsearch unavailable or no legal articles to index")
    finally:
        try:
            await get_client().close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
