import hashlib
import json
import uuid
from decimal import Decimal

from app.db.models import Contract


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


def stub_signature(contract_hash_value: str, request_id: uuid.UUID) -> tuple[str, str, str]:
    certificate = (
        "-----BEGIN CERTIFICATE-----\n"
        f"EIMZO-STUB-{request_id}\n"
        "-----END CERTIFICATE-----"
    )
    signature = f"EIMZO-STUB-SIGNATURE:{request_id}:{contract_hash_value}"
    thumbprint = hashlib.sha256(certificate.encode("utf-8")).hexdigest().upper()[:40]
    return signature, certificate, thumbprint
