"""Pydantic-схемы API.

Базовый набор для Week 1-2; полные схемы контрактов и агентов
добавляются на Weeks 5-8 вместе с соответствующими эндпоинтами.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# Потолок на текст документа. Совпадает с лимитом извлечения из файла
# (utils/document_parser.MAX_EXTRACTED_CHARS): JSON-путь создания договора
# раньше не ограничивался ничем, и через него в базу заезжали документы,
# на которых разбор и сравнение версий занимали минуты.
MAX_CONTENT_CHARS = 2_000_000


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    username: str
    full_name: str | None = None
    role: str
    organization_id: uuid.UUID | None = None
    is_active: bool
    mfa_enabled: bool = False


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
    invite_code: str
    storage_limit: int
    compliance_policies: str | None = None
    created_at: datetime


class ProjectCreate(BaseModel):
    name: str
    client: str | None = None
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    client: str | None = None
    description: str | None = None
    status: str | None = None  # active | closed


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    client: str | None = None
    description: str | None = None
    status: str
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    contracts_count: int = 0


class ContractCreate(BaseModel):
    title: str = Field(max_length=512)
    contract_type: str
    counterparty: str | None = Field(default=None, max_length=512)
    content: str | None = Field(default=None, max_length=MAX_CONTENT_CHARS)
    amount: float | None = None
    currency: str = "UZS"
    project_id: uuid.UUID | None = None
    # Текст создан ИИ — документ заводится со статусом «Сгенерирован»
    # (ТЗ, раздел 3.1, шаг 4), а не «Черновик».
    ai_generated: bool = False


class ContractUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=512)
    counterparty: str | None = Field(default=None, max_length=512)
    content: str | None = Field(default=None, max_length=MAX_CONTENT_CHARS)
    amount: float | None = None
    currency: str | None = None
    changes_description: str | None = None


class LabelSummary(BaseModel):
    """Плашка в списке документов. Название и цвет фронт берёт из своего
    каталога по kind — здесь только данные, зависящие от документа."""

    model_config = ConfigDict(from_attributes=True)

    kind: str
    actor_type: str
    actor_name: str | None = None
    actor_role: str | None = None
    created_at: datetime


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    contract_type: str | None = None
    counterparty: str | None = None
    status: str
    risk_score: int | None = None
    project_id: uuid.UUID | None = None
    labels: list[LabelSummary] = []
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


# --------------------------------------------------------------------------
# Правовой движок: пункты, вердикты, решения юриста (ТЗ, раздел 4)
# --------------------------------------------------------------------------


class ClauseSourceOut(BaseModel):
    """Норма, на которую опирается вердикт, со снимком редакции на дату
    проверки — без неё результат проверки невоспроизводим."""

    document_title: str | None = None
    document_number: str | None = None
    article_number: str | None = None
    article_title: str | None = None
    content: str | None = None
    url: str | None = None
    current_revision_date: str | None = None
    status: str | None = None


class ClauseCheckOut(BaseModel):
    verdict: str
    rationale: str | None = None
    suggested_text: str | None = None
    sources: list[ClauseSourceOut] = []
    checked_on: date | None = None
    created_at: datetime | None = None
    # Текст пункта изменился после проверки: вердикт относится к прежней
    # редакции и полагаться на него нельзя.
    stale: bool = False


class ClauseDecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    comment: str | None = None
    new_text: str | None = None
    decided_by: uuid.UUID | None = None
    decided_by_name: str | None = None
    created_at: datetime
    # Решение принято по другой редакции пункта: текст изменили после него.
    stale: bool = False


class ClauseOut(BaseModel):
    id: uuid.UUID
    anchor: str
    number: str | None = None
    level: int
    title: str | None = None
    content: str
    position: int
    parent_anchor: str | None = None
    check: ClauseCheckOut | None = None
    decision: ClauseDecisionOut | None = None
    comments_count: int = 0


class ClauseListOut(BaseModel):
    contract_id: uuid.UUID
    status: str
    locked: bool
    progress: dict
    items: list[ClauseOut]


class ClauseDecisionIn(BaseModel):
    action: str  # confirm | edit | comment | defer
    comment: str | None = None
    new_text: str | None = None


class ReviewStartIn(BaseModel):
    # Пустой список означает «запустить все три модуля».
    modules: list[str] = []
    party_side: str | None = None


class ReviewRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    module: str
    status: str
    party_side: str | None = None
    clauses_total: int = 0
    findings_total: int = 0
    summary: str | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class LogicFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: str
    category_title: str | None = None
    description: str
    suggestion: str | None = None
    clause_anchors: list[str] = []
    detected_by: str
    status: str
    resolution_note: str | None = None
    resolved_by: uuid.UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime


class RiskFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: str
    category_title: str | None = None
    level: str
    level_title: str | None = None
    description: str
    consequence: str | None = None
    mitigation: str | None = None
    clause_anchors: list[str] = []
    status: str
    resolved_at: datetime | None = None
    created_at: datetime


class FindingResolveIn(BaseModel):
    status: str  # accepted | rejected | fixed | open
    note: str | None = None


class CommentCreate(BaseModel):
    text: str
    clause_id: uuid.UUID | None = None


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contract_id: uuid.UUID
    clause_id: uuid.UUID | None = None
    clause_anchor: str | None = None
    text: str
    author_id: uuid.UUID | None = None
    author_name: str | None = None
    author_role: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime


# --------------------------------------------------------------------------
# База шаблонов (ТЗ, раздел 6)
# --------------------------------------------------------------------------


class TemplateCreate(BaseModel):
    name: str = Field(max_length=512)
    doc_type: str
    content: str = Field(max_length=MAX_CONTENT_CHARS)
    description: str | None = None


class TemplateFromContractIn(BaseModel):
    name: str | None = None
    description: str | None = None


class TemplateUpdate(BaseModel):
    name: str | None = None
    doc_type: str | None = None
    content: str | None = None
    description: str | None = None
    is_archived: bool | None = None


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    doc_type: str
    doc_type_title: str | None = None
    description: str | None = None
    actualized_at: date | None = None
    verified_by: uuid.UUID | None = None
    verified_by_name: str | None = None
    verified_at: datetime | None = None
    stale_reason: str | None = None
    stale_since: datetime | None = None
    is_archived: bool = False
    created_by: uuid.UUID | None = None
    created_by_name: str | None = None
    created_at: datetime
    updated_at: datetime


class TemplateDetail(TemplateOut):
    content: str


# --------------------------------------------------------------------------
# Проект: контекст и участники (ТЗ, раздел 1)
# --------------------------------------------------------------------------


class ProjectContextIn(BaseModel):
    """Общий контекст проекта, наследуемый документами при генерации."""

    our_party: str | None = None
    counterparty: str | None = None
    parties_note: str | None = None
    amount: float | None = None
    currency: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    jurisdiction: str | None = None
    notes: str | None = None


class ProjectMemberIn(BaseModel):
    user_id: uuid.UUID
    access: str = "write"  # read | comment | write


class ProjectMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    access: str
    full_name: str | None = None
    email: str | None = None
    role: str | None = None
    created_at: datetime


# --------------------------------------------------------------------------
# Версии, экспорт, создание документа (ТЗ, разделы 3 и 5)
# --------------------------------------------------------------------------


class VersionDiffOut(BaseModel):
    from_version: int
    to_version: int
    blocks: list[dict]
    summary: dict


class VersionRestoreIn(BaseModel):
    comment: str | None = None


class DuplicateContractIn(BaseModel):
    title: str | None = None
    counterparty: str | None = None
    project_id: uuid.UUID | None = None
    # Результаты проверок и решения юриста в копию не переносятся: это другой
    # договор с другими сторонами, чужое подтверждение к нему не относится.


class DraftParamsIn(BaseModel):
    requirements: str
    contract_type: str | None = None
    project_id: uuid.UUID | None = None


class DraftParamsOut(BaseModel):
    """Карточка параметров, которую юрист подтверждает перед генерацией."""

    contract_type: str | None = None
    parties: list[dict] = []
    subject: str | None = None
    amount: str | None = None
    currency: str | None = None
    payment_terms: str | None = None
    deadlines: list[dict] = []
    penalties: list[dict] = []
    jurisdiction: str | None = None
    other_terms: list[str] = []
    transcript: str | None = None
