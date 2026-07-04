"""Pydantic-схемы API.

Базовый набор для Week 1-2; полные схемы контрактов и агентов
добавляются на Weeks 5-8 вместе с соответствующими эндпоинтами.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    username: str
    full_name: str | None = None
    role: str
    is_active: bool


class ContractCreate(BaseModel):
    title: str
    contract_type: str
    counterparty: str | None = None
    content: str | None = None
    amount: float | None = None
    currency: str = "UZS"


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    contract_type: str | None = None
    counterparty: str | None = None
    status: str
    risk_score: int | None = None
    created_at: datetime
