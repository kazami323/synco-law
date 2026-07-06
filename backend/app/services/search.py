"""Полнотекстовый поиск по контрактам (Phase 2, Elasticsearch).

Индекс один на всех, изоляция организаций — фильтром по org_id.
Если Elasticsearch недоступен, вызывающий код падает обратно на SQL ILIKE —
приложение работает и без поискового кластера.
"""

import logging
from datetime import date

from elasticsearch import AsyncElasticsearch

from app.core.config import settings
from app.db.models import Contract

logger = logging.getLogger("app.search")

INDEX = "contracts"

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
                # Штатный russian-стеммер: работает для ru/uz-кириллицы
                "russian_morphology_stub": {"type": "stemmer", "language": "russian"}
            },
        }
    },
    "mappings": {
        "properties": {
            "org_id": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "ru"},
            "content": {"type": "text", "analyzer": "ru"},
            "counterparty": {
                "type": "text",
                "analyzer": "ru",
                "fields": {"raw": {"type": "keyword"}},
            },
            "contract_type": {"type": "keyword"},
            "status": {"type": "keyword"},
            "risk_score": {"type": "integer"},
            "amount": {"type": "double"},
            "currency": {"type": "keyword"},
            "created_by": {"type": "keyword"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
        }
    },
}

_client: AsyncElasticsearch | None = None


def get_client() -> AsyncElasticsearch:
    global _client
    if _client is None:
        _client = AsyncElasticsearch(
            settings.ELASTICSEARCH_URL, request_timeout=5, retry_on_timeout=False
        )
    return _client


async def es_available() -> bool:
    try:
        return await get_client().ping()
    except Exception:
        return False


async def ensure_index() -> bool:
    """Создаёт индекс с маппингом, если его ещё нет."""
    try:
        client = get_client()
        if not await client.indices.exists(index=INDEX):
            await client.indices.create(index=INDEX, **MAPPING)
            logger.info("search index created")
        return True
    except Exception:
        logger.warning("elasticsearch unavailable, search runs on SQL fallback")
        return False


def _doc(contract: Contract) -> dict:
    return {
        "org_id": str(contract.organization_id),
        "title": contract.title,
        "content": contract.content or "",
        "counterparty": contract.counterparty or "",
        "contract_type": contract.contract_type,
        "status": contract.status,
        "risk_score": contract.risk_score,
        "amount": float(contract.amount) if contract.amount is not None else None,
        "currency": contract.currency,
        "created_by": str(contract.created_by) if contract.created_by else None,
        "created_at": contract.created_at.isoformat() if contract.created_at else None,
        "updated_at": contract.updated_at.isoformat() if contract.updated_at else None,
    }


async def index_contract(contract: Contract) -> None:
    """Индексирует контракт; молча пропускает, если ES недоступен."""
    try:
        await get_client().index(
            index=INDEX, id=str(contract.id), document=_doc(contract)
        )
    except Exception:
        logger.debug("skip indexing: elasticsearch unavailable")


async def delete_from_index(contract_id) -> None:
    try:
        await get_client().delete(index=INDEX, id=str(contract_id), ignore=[404])
    except Exception:
        logger.debug("skip delete from index: elasticsearch unavailable")


async def search_contracts(
    *,
    org_id,
    q: str | None,
    contract_type: str | None = None,
    status: str | None = None,
    risk: str | None = None,  # high | medium | low
    counterparty: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    created_by: str | None = None,  # для ролей view_assigned
    page: int = 1,
    size: int = 10,
) -> dict:
    """Поиск с подсветкой. Бросает исключение, если ES недоступен."""
    filters: list[dict] = [{"term": {"org_id": str(org_id)}}]
    if contract_type:
        filters.append({"term": {"contract_type": contract_type}})
    if status:
        filters.append({"term": {"status": status}})
    if created_by:
        filters.append({"term": {"created_by": created_by}})
    if counterparty:
        filters.append(
            {"match": {"counterparty": {"query": counterparty, "operator": "and"}}}
        )
    if risk == "high":
        filters.append({"range": {"risk_score": {"gt": 70}}})
    elif risk == "medium":
        filters.append({"range": {"risk_score": {"gte": 40, "lte": 70}}})
    elif risk == "low":
        filters.append({"range": {"risk_score": {"lt": 40}}})
    if date_from or date_to:
        rng: dict = {}
        if date_from:
            rng["gte"] = date_from.isoformat()
        if date_to:
            rng["lte"] = date_to.isoformat()
        filters.append({"range": {"created_at": rng}})

    if q:
        must: dict = {
            "multi_match": {
                "query": q,
                "fields": ["title^3", "counterparty^2", "content"],
                "operator": "and",
                "fuzziness": "AUTO",
            }
        }
        sort = ["_score"]
    else:
        must = {"match_all": {}}
        sort = [{"created_at": {"order": "desc"}}]

    response = await get_client().search(
        index=INDEX,
        query={"bool": {"must": must, "filter": filters}},
        highlight={
            # Экранируем HTML из текста контрактов — сниппеты рендерятся как HTML
            "encoder": "html",
            "fields": {
                "content": {
                    "fragment_size": 160,
                    "number_of_fragments": 2,
                    "pre_tags": ["<mark>"],
                    "post_tags": ["</mark>"],
                },
                "title": {"pre_tags": ["<mark>"], "post_tags": ["</mark>"]},
            }
        },
        from_=(page - 1) * size,
        size=size,
        sort=sort,
    )

    hits = response["hits"]
    return {
        "total": hits["total"]["value"],
        "items": [
            {
                "id": hit["_id"],
                "title": hit["_source"]["title"],
                "title_highlight": (hit.get("highlight", {}).get("title") or [None])[0],
                "snippets": hit.get("highlight", {}).get("content", []),
                "counterparty": hit["_source"].get("counterparty") or None,
                "contract_type": hit["_source"].get("contract_type"),
                "status": hit["_source"].get("status"),
                "risk_score": hit["_source"].get("risk_score"),
                "created_at": hit["_source"].get("created_at"),
                "updated_at": hit["_source"].get("updated_at"),
            }
            for hit in hits["hits"]
        ],
        "engine": "elasticsearch",
    }
