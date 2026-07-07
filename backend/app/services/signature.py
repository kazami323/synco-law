import hashlib
import json
import logging
import uuid
from decimal import Decimal

import httpx

from app.core.config import settings
from app.db.models import Contract

logger = logging.getLogger("app.signature")


def contract_hash(contract: Contract) -> str:
    payload = {
        "id": str(contract.id),
        "title": contract.title,
        "counterparty": contract.counterparty,
        "content": contract.content,
        "amount": str(contract.amount) if isinstance(contract.amount, Decimal) else contract.amount,
        "currency": contract.currency,
        "status": contract.status,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def verify_pkcs7_via_dsv(pkcs7: str) -> bool | None:
    """Серверная проверка подписи через E-IMZO DSV.

    None — DSV не настроен (EIMZO_DSV_URL пуст), подпись сохраняется как
    есть; True/False — вердикт DSV. Развёрнутый e-imzo-server принимает
    POST {"pkcs7": ...} и отвечает {"success": true/false}.
    """
    if not settings.EIMZO_DSV_URL:
        return None
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                settings.EIMZO_DSV_URL, json={"pkcs7": pkcs7}
            )
            response.raise_for_status()
            return bool(response.json().get("success"))
    except Exception:
        logger.exception("DSV verification failed")
        return False


def stub_signature(contract_hash_value: str, request_id: uuid.UUID) -> tuple[str, str, str]:
    certificate = (
        "-----BEGIN CERTIFICATE-----\n"
        f"EIMZO-STUB-{request_id}\n"
        "-----END CERTIFICATE-----"
    )
    signature = f"EIMZO-STUB-SIGNATURE:{request_id}:{contract_hash_value}"
    thumbprint = hashlib.sha256(certificate.encode("utf-8")).hexdigest().upper()[:40]
    return signature, certificate, thumbprint
