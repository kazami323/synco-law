import hashlib
import hmac
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


async def verify_pkcs7_via_dsv(
    pkcs7: str, expected_contract_hash: str | None = None
) -> bool | None:
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
                settings.EIMZO_DSV_URL,
                json={"pkcs7": pkcs7, "expected_hash": expected_contract_hash},
            )
            response.raise_for_status()
            payload = response.json()
            if not bool(payload.get("success")):
                return False
            if expected_contract_hash and settings.EIMZO_REQUIRE_CONTENT_BINDING:
                signed_hash = (
                    payload.get("signed_data_hash")
                    or payload.get("document_hash")
                    or payload.get("verified_hash")
                )
                if not signed_hash or not hmac.compare_digest(
                    str(signed_hash).lower(), expected_contract_hash.lower()
                ):
                    logger.error("DSV did not prove signature binding to contract hash")
                    return False
            return True
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
