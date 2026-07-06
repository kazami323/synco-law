"""Pydantic-схемы API.

Базовый набор для Week 1-2; полные схемы контрактов и агентов
добавляются на Weeks 5-8 вместе с соответствующими эндпоинтами.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    username: str
    full_name: str | None = None
    role: str
    organization_id: uuid.UUID | None = None
    is_active: bool


class OrganizationCreate(BaseModel):
    name: str
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None


class OrganizationUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None
    compliance_policies: str | None = None


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    country: str
    storage_limit: int
    compliance_policies: str | None = None
    created_at: datetime


class ContractCreate(BaseModel):
    title: str
    contract_type: str
    counterparty: str | None = None
    content: str | None = None
    amount: float | None = None
    currency: str = "UZS"


class ContractUpdate(BaseModel):
    title: str | None = None
    counterparty: str | None = None
    content: str | None = None
    amount: float | None = None
    currency: str | None = None
    changes_description: str | None = None


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    contract_type: str | None = None
    counterparty: str | None = None
    status: str
    risk_score: int | None = None
    created_at: datetime
    updated_at: datetime


class ContractDetail(ContractOut):
    content: str | None = None
    file_path: str | None = None
    amount: float | None = None
    currency: str
    created_by: uuid.UUID | None = None
    signed_at: datetime | None = None
    signed_by: uuid.UUID | None = None
    signature: str | None = None
    signature_timestamp: datetime | None = None
    certificate_thumbprint: str | None = None


class ContractVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    changes_description: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime


class SignRequestOut(BaseModel):
    request_id: uuid.UUID
    hash: str


class SignConfirmIn(BaseModel):
    request_id: uuid.UUID | None = None
    signature: str | None = None
    certificate: str | None = None
    certificate_thumbprint: str | None = None
    pin: str | None = None


class SignConfirmOut(BaseModel):
    signature: str
    timestamp: datetime
    certificate_thumbprint: str


class ContractDeadlineCreate(BaseModel):
    deadline_date: date
    type: str = "other"


class ContractDeadlineOut(BaseModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    deadline_date: date
    type: str
    days_left: int
    is_notified: bool


class UpcomingDeadlineOut(BaseModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    contract_title: str
    deadline_date: date
    type: str
    days_left: int


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    contract_id: uuid.UUID | None = None
    text: str
    read_at: datetime | None = None
    created_at: datetime
    contract_title: str | None = None
