"""Переиндексация всех контрактов в Elasticsearch.

Запуск: .venv\\Scripts\\python.exe -m scripts.reindex_search
"""

import asyncio

from sqlalchemy import select

from app.db.base import async_session_factory
from app.db.models import Contract
from app.services.search import ensure_index, es_available, get_client, index_contract


async def main() -> None:
    try:
        if not await es_available():
            print("Elasticsearch недоступен — docker compose --profile search up -d")
            return
        await ensure_index()
        async with async_session_factory() as session:
            contracts = (await session.execute(select(Contract))).scalars().all()
            for contract in contracts:
                await index_contract(contract)
            print(f"Проиндексировано контрактов: {len(contracts)}")
    finally:
        await get_client().close()


if __name__ == "__main__":
    asyncio.run(main())
