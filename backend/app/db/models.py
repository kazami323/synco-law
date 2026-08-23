import enum
import secrets
import uuid
from datetime import date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Размерность эмбеддингов для семантического поиска (voyage-3 / text-embedding-3-small)
EMBEDDING_DIM = 1536


def make_invite_code() -> str:
    return secrets.token_hex(5).upper()


class Role(str, enum.Enum):
    ADMIN = "admin"
    HEAD = "head"  # Руководитель отдела
    SENIOR_LAWYER = "senior_lawyer"
    LAWYER = "lawyer"
    COMPLIANCE = "compliance"
    FINANCE = "finance"
    OBSERVER = "observer"  # Наблюдатель по ТЗ: смотрит и комментирует
    EXTERNAL = "external"


class ContractStatus(str, enum.Enum):
    """Статусы документа по ТЗ «Правовой движок», раздел 2.

    Значения в БД оставлены прежними там, где смысл совпал (analyzing =
    «На проверке», analyzed = «Проверен», approved = «Подтверждён юристом»,
    ready_to_sign = «Финальный»), чтобы не переписывать исторические данные.
    approved_finance и signed — надстройка проекта над ТЗ (финансовое
    согласование и E-IMZO).
    """

    DRAFT = "draft"  # Черновик
    GENERATED = "generated"  # Сгенерирован ИИ, проверки не проводились
    ANALYZING = "analyzing"  # На проверке
    ANALYZED = "analyzed"  # Проверен
    APPROVED = "approved"  # Подтверждён юристом
    NEEDS_REVISION = "needs_revision"  # На доработке
    APPROVED_FINANCE = "approved_finance"
    READY_TO_SIGN = "ready_to_sign"  # Финальный: редактирование заблокировано
    SIGNED = "signed"
    ARCHIVED = "archived"  # В архиве


# В этих статусах текст документа править нельзя (ТЗ: «Финальный — готов к
# подписанию, редактирование заблокировано»).
LOCKED_STATUSES: frozenset[str] = frozenset(
    {
        ContractStatus.READY_TO_SIGN.value,
        ContractStatus.SIGNED.value,
        ContractStatus.ARCHIVED.value,
    }
)


class ContractType(str, enum.Enum):
    """Тип документа в проекте.

    Каталог типов по ТЗ (раздел 3.1) плюс продукты работы юриста и агентов:
    риск-карта, правовое заключение, проверка контракта. Человеческие названия
    и обязательные блоки — в app/core/document_types.py.
    """

    SUPPLY = "supply"  # договор поставки
    SERVICE = "service"  # оказание услуг
    CONTRACTING = "contracting"  # подряд
    LEASE = "lease"  # аренда
    PURCHASE = "purchase"  # купля-продажа
    EMPLOYMENT = "employment"  # трудовой
    NDA = "nda"
    LICENSE = "license"  # лицензионный
    AMENDMENT = "amendment"  # дополнительное соглашение
    RISK_MAP = "risk_map"
    LEGAL_OPINION = "legal_opinion"
    CONTRACT_REVIEW = "contract_review"
    OTHER = "other"


class ClauseVerdict(str, enum.Enum):
    """Вердикт Модуля 1 по пункту. Закрытый список из ТЗ, раздел 4."""

    COMPLIANT = "compliant"  # соответствует
    CONFLICTS = "conflicts"  # противоречит
    ATTENTION = "attention"  # требует внимания
    NO_NORM = "no_norm"  # норма не найдена


class ClauseDecisionAction(str, enum.Enum):
    """Решение юриста по пункту (ТЗ, раздел 4, Модуль 1)."""

    CONFIRM = "confirm"  # подтвердить
    EDIT = "edit"  # изменить
    COMMENT = "comment"  # комментарий
    DEFER = "defer"  # отложить


class ReviewModule(str, enum.Enum):
    CLAUSES = "clauses"  # Модуль 1
    LOGIC = "logic"  # Модуль 2
    RISKS = "risks"  # Модуль 3


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(512))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(64))
    address: Mapped[str | None] = mapped_column(String(1024))
    country: Mapped[str] = mapped_column(String(128), server_default="Uzbekistan")
    storage_limit: Mapped[int] = mapped_column(Integer, server_default="1000")  # GB
    invite_code: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, default=make_invite_code
    )
    # Внутренние комплаенс-политики: их проверяет Compliance Agent (Phase 2)
    compliance_policies: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    users: Mapped[list["User"]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(128), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32), server_default=Role.LAWYER.value)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id")
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    # Секрет-кандидат при перенастройке MFA. Пока пользователь не подтвердил
    # его кодом, действующий секрет и признак mfa_enabled не трогаются —
    # иначе один запрос к /mfa/setup молча снимал бы второй фактор.
    mfa_pending_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    # Telegram-уведомления: chat_id после привязки, link_code — одноразовый код
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64))
    telegram_link_code: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow
    )

    organization: Mapped[Organization | None] = relationship(back_populates="users")


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class Project(Base):
    """Проект (дело/заказ): папка, в которой юрист ведёт договоры и
    документы одного клиента или заказа."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(Text)
    client: Mapped[str | None] = mapped_column(String(512))  # заказчик
    status: Mapped[str] = mapped_column(
        String(32), server_default="active", index=True
    )  # active | closed
    # Общий контекст проекта по ТЗ (раздел 1): стороны, суммы, сроки.
    # Наследуется документами при генерации, чтобы юрист не вводил одно и то же
    # в каждый договор. Структура — app/core/project_context.py.
    context: Mapped[dict | None] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow
    )

    contracts: Mapped[list["Contract"]] = relationship(back_populates="project")
    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectMember(Base):
    """Участник проекта с правом доступа (ТЗ, раздел 1).

    Ограничивает доступ внутри организации: если у проекта есть хотя бы один
    участник, видеть его могут только участники (плюс роли с view_all).
    access: read — просмотр, comment — просмотр и комментарии, write — работа.
    """

    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    access: Mapped[str] = mapped_column(String(16), server_default="write")
    added_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    project: Mapped[Project] = relationship(back_populates="members")


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(512))
    contract_type: Mapped[str | None] = mapped_column(String(64))
    counterparty: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(
        String(32), server_default=ContractStatus.DRAFT.value, index=True
    )
    content: Mapped[str | None] = mapped_column(Text)  # Полный текст контракта
    file_path: Mapped[str | None] = mapped_column(String(1024))  # Путь в MinIO
    content_vector = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(8), server_default="UZS")
    risk_score: Mapped[int | None] = mapped_column(Integer)  # 0-100
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sql_text("now()"), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow
    )
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    signature: Mapped[str | None] = mapped_column(Text)
    signature_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signature_certificate: Mapped[str | None] = mapped_column(Text)
    certificate_thumbprint: Mapped[str | None] = mapped_column(String(128))

    project: Mapped[Project | None] = relationship(back_populates="contracts")
    versions: Mapped[list["ContractVersion"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )
    agent_results: Mapped[list["AgentResult"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )
    workflow_states: Mapped[list["WorkflowState"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )
    # lazy="selectin": плашки нужны почти везде, где показывается документ,
    # а ленивая подгрузка в async-сессии падает с MissingGreenlet при
    # сериализации ответа (в т.ч. сразу после создания документа).
    labels: Mapped[list["DocumentLabel"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan", lazy="selectin"
    )
    clauses: Mapped[list["Clause"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    review_runs: Mapped[list["ReviewRun"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    comments: Mapped[list["DocumentComment"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    deadlines: Mapped[list["ContractDeadline"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )
    sign_requests: Mapped[list["SignRequest"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )


class SignRequest(Base):
    __tablename__ = "sign_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    contract_hash: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    contract: Mapped[Contract] = relationship(back_populates="sign_requests")


class ContractDeadline(Base):
    __tablename__ = "contract_deadlines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    deadline_date: Mapped[date] = mapped_column(Date, index=True)
    deadline_type: Mapped[str] = mapped_column("type", String(64), server_default="other")
    is_notified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    contract: Mapped[Contract] = relationship(back_populates="deadlines")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(String(1024))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sql_text("now()"), index=True
    )

    contract: Mapped[Contract | None] = relationship(back_populates="notifications")


class ContractVersion(Base):
    __tablename__ = "contract_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str | None] = mapped_column(Text)
    changes_description: Mapped[str | None] = mapped_column(String(1024))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    contract: Mapped[Contract] = relationship(back_populates="versions")


class AgentResult(Base):
    __tablename__ = "agent_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    agent_name: Mapped[str] = mapped_column(String(64))  # contract_analyzer, law_agent, ...
    result_type: Mapped[str | None] = mapped_column(String(64))
    result_data: Mapped[dict | None] = mapped_column(JSONB)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    contract: Mapped[Contract] = relationship(back_populates="agent_results")


class WorkflowState(Base):
    __tablename__ = "workflow_states"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    current_stage: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comments: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    contract: Mapped[Contract] = relationship(back_populates="workflow_states")


class DocumentLabel(Base):
    """Отметка («плашка») на документе: кто и что с ним сделал.

    В отличие от линейного статуса договора, отметок на документе может висеть
    несколько одновременно — «Проверено ИИ», «Подготовлено», «Утверждено», —
    и каждая помнит автора (агента или юриста), его роль и время.
    Уникальность по (документ, вид) — плашка либо стоит, либо нет; повторная
    простановка обновляет автора, а история изменений остаётся в audit_log.
    """

    __tablename__ = "document_labels"
    __table_args__ = (
        UniqueConstraint("contract_id", "kind", name="uq_document_label_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(64), index=True)
    actor_type: Mapped[str] = mapped_column(String(16))  # agent | user
    actor_agent: Mapped[str | None] = mapped_column(String(64))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    # Снимок роли и имени на момент простановки: если человеку позже сменят
    # должность, старая плашка не должна «переписываться» задним числом.
    actor_role: Mapped[str | None] = mapped_column(String(32))
    actor_name: Mapped[str | None] = mapped_column(String(256))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )

    contract: Mapped[Contract] = relationship(back_populates="labels")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    action: Mapped[str] = mapped_column(String(128))
    resource_type: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    changes: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class AgentChatSession(Base):
    __tablename__ = "agent_chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    agent: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(256), server_default="Новый чат")
    messages: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="SET NULL"), index=True
    )
    document_name: Mapped[str | None] = mapped_column(String(512))
    document_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow, index=True
    )


class AIUsageLog(Base):
    __tablename__ = "ai_usage_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    endpoint: Mapped[str] = mapped_column(String(128), index=True)
    agent: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )


class LegalDocument(Base):
    """Source legal act imported from public legal databases such as lex.uz."""

    __tablename__ = "legal_documents"
    __table_args__ = (
        UniqueConstraint(
            "source", "source_id", "language", name="uq_legal_documents_source_lang"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source: Mapped[str] = mapped_column(String(64), server_default="lex.uz", index=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    language: Mapped[str] = mapped_column(String(16), server_default="ru", index=True)
    jurisdiction: Mapped[str] = mapped_column(String(128), server_default="Uzbekistan")
    doc_type: Mapped[str | None] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(1024))
    number: Mapped[str | None] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(2048))
    adopted_at: Mapped[date | None] = mapped_column(Date)
    effective_at: Mapped[date | None] = mapped_column(Date)
    current_revision_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(32), server_default="active", index=True)
    extra_data: Mapped[dict | None] = mapped_column("metadata", JSONB)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow
    )

    articles: Mapped[list["LegalArticle"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class LegalArticle(Base):
    """Article-level chunk used by Law Agent retrieval."""

    __tablename__ = "legal_articles"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "source_article_id", name="uq_legal_articles_source_article"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_documents.id", ondelete="CASCADE"), index=True
    )
    source_article_id: Mapped[str | None] = mapped_column(String(128), index=True)
    article_number: Mapped[str | None] = mapped_column(String(64), index=True)
    title: Mapped[str | None] = mapped_column(String(1024))
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    content_vector = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    position: Mapped[int] = mapped_column(Integer, server_default="0", index=True)
    url: Mapped[str | None] = mapped_column(String(2048))
    extra_data: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow
    )

    document: Mapped[LegalDocument] = relationship(back_populates="articles")


# --------------------------------------------------------------------------
# Правовой движок: работа по пунктам (ТЗ, раздел 4)
#
# Единица работы — пункт, а не документ целиком. Документ режется на дерево
# раздел → пункт → подпункт; к каждому пункту привязываются найденные нормы,
# вердикт системы и решение юриста.
# --------------------------------------------------------------------------


class Clause(Base):
    """Структурная единица документа: раздел, пункт или подпункт."""

    __tablename__ = "clauses"
    __table_args__ = (
        UniqueConstraint("contract_id", "anchor", name="uq_clause_anchor"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clauses.id", ondelete="CASCADE"), index=True
    )
    # Стабильный якорь пункта: нумерация из текста («5.4») либо сгенерированный
    # суррогат («§3»). По нему решения юриста переносятся между версиями.
    anchor: Mapped[str] = mapped_column(String(64), index=True)
    number: Mapped[str | None] = mapped_column(String(64))
    level: Mapped[int] = mapped_column(Integer, server_default="1")  # 1 раздел, 2 пункт
    title: Mapped[str | None] = mapped_column(String(1024))
    content: Mapped[str] = mapped_column(Text)
    # Хеш нормализованного текста: если текст не менялся, решение юриста
    # переносится в новую версию автоматически, иначе требует пересмотра.
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    position: Mapped[int] = mapped_column(Integer, server_default="0", index=True)
    # Границы пункта в тексте документа. Правка пункта вставляется по ним на
    # своё место: пересборка документа из пунктов теряла «Раздел», римскую
    # нумерацию и маркеры подпунктов.
    start_offset: Mapped[int] = mapped_column(Integer, server_default="0")
    end_offset: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow
    )

    contract: Mapped[Contract] = relationship(back_populates="clauses")
    children: Mapped[list["Clause"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan", passive_deletes=True
    )
    parent: Mapped["Clause | None"] = relationship(
        back_populates="children", remote_side="Clause.id"
    )
    checks: Mapped[list["ClauseCheck"]] = relationship(
        back_populates="clause", cascade="all, delete-orphan", passive_deletes=True
    )
    decisions: Mapped[list["ClauseDecision"]] = relationship(
        back_populates="clause", cascade="all, delete-orphan", passive_deletes=True
    )


class ReviewRun(Base):
    """Один запуск модуля проверки. Модули запускаются по отдельности или все
    сразу (ТЗ, раздел 4), поэтому у каждого свой прогон со своим статусом."""

    __tablename__ = "review_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    module: Mapped[str] = mapped_column(String(16), index=True)  # clauses|logic|risks
    status: Mapped[str] = mapped_column(
        String(16), server_default="running", index=True
    )  # running | done | failed
    # Модуль 3 без стороны не запускается: сторона меняет всю оптику анализа.
    party_side: Mapped[str | None] = mapped_column(String(256))
    clauses_total: Mapped[int] = mapped_column(Integer, server_default="0")
    findings_total: Mapped[int] = mapped_column(Integer, server_default="0")
    # Резюме Модуля 3: «что критично поправить до подписания» (ТЗ, раздел 4).
    # Модель его возвращала, но оно нигде не сохранялось.
    summary: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    started_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    contract: Mapped[Contract] = relationship(back_populates="review_runs")


class ClauseCheck(Base):
    """Результат сверки пункта с правовой базой (Модуль 1).

    sources хранит снапшот норм на дату проверки: номер статьи, текст, ссылку
    и редакцию. Снапшот, а не ссылка на legal_articles, — потому что ТЗ требует
    воспроизводимости результата после обновления законодательства.
    """

    __tablename__ = "clause_checks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    clause_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clauses.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("review_runs.id", ondelete="SET NULL"), index=True
    )
    verdict: Mapped[str] = mapped_column(String(16), index=True)
    rationale: Mapped[str | None] = mapped_column(Text)
    suggested_text: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[list | None] = mapped_column(JSONB)
    # Хеш текста пункта на момент проверки. Без него вердикт не устаревал
    # вместе с текстом: юрист правил пункт и продолжал видеть «соответствует»,
    # вынесенное по прежней редакции. У решения юриста такой хеш был с самого
    # начала (ClauseDecision.clause_hash), у вердикта — нет.
    clause_hash: Mapped[str | None] = mapped_column(String(64))
    checked_on: Mapped[date] = mapped_column(Date, server_default=text("CURRENT_DATE"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )

    clause: Mapped[Clause] = relationship(back_populates="checks")


class ClauseDecision(Base):
    """Решение юриста по пункту: подтвердить / изменить / комментарий /
    отложить. Фиксируется с автором и временем — требование ТЗ."""

    __tablename__ = "clause_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    clause_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clauses.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(16), index=True)
    comment: Mapped[str | None] = mapped_column(Text)
    previous_text: Mapped[str | None] = mapped_column(Text)
    new_text: Mapped[str | None] = mapped_column(Text)
    # Текст пункта на момент решения: если пункт потом поменяли, подтверждение
    # больше не действует и юрист должен пройти по нему заново.
    clause_hash: Mapped[str | None] = mapped_column(String(64))
    # Актуально только последнее решение по пункту; прошлые остаются историей.
    is_current: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), index=True
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    decided_by_name: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )

    clause: Mapped[Clause] = relationship(back_populates="decisions")


class LogicFinding(Base):
    """Расхождение внутри документа (Модуль 2).

    clause_anchors — минимум два конфликтующих пункта: ТЗ требует показывать их
    рядом, находка с одним пунктом бессмысленна.
    """

    __tablename__ = "logic_findings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("review_runs.id", ondelete="SET NULL"), index=True
    )
    category: Mapped[str] = mapped_column(String(32), index=True)
    description: Mapped[str] = mapped_column(Text)
    suggestion: Mapped[str | None] = mapped_column(Text)
    clause_anchors: Mapped[list | None] = mapped_column(JSONB)
    detected_by: Mapped[str] = mapped_column(String(16), server_default="rule")
    status: Mapped[str] = mapped_column(
        String(16), server_default="open", index=True
    )  # open | accepted | rejected | fixed
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )


class RiskFinding(Base):
    """Риск из Модуля 3 — с уровнем, последствиями и предложением."""

    __tablename__ = "risk_findings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("review_runs.id", ondelete="SET NULL"), index=True
    )
    category: Mapped[str] = mapped_column(String(32), index=True)
    level: Mapped[str] = mapped_column(String(16), index=True)  # high | medium | low
    description: Mapped[str] = mapped_column(Text)
    consequence: Mapped[str | None] = mapped_column(Text)  # последствия на практике
    mitigation: Mapped[str | None] = mapped_column(Text)  # предложение по устранению
    clause_anchors: Mapped[list | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), server_default="open", index=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )


class DocumentComment(Base):
    """Комментарий к документу или пункту.

    Нужен роли «Наблюдатель» (ТЗ, раздел 7): смотреть и комментировать, но не
    менять статусы.
    """

    __tablename__ = "document_comments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    clause_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clauses.id", ondelete="CASCADE"), index=True
    )
    # Колонка называется text и перекрывает импортированный sqlalchemy.text
    # внутри тела класса — ниже по классу используется алиас sql_text.
    text: Mapped[str] = mapped_column(Text)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    author_name: Mapped[str | None] = mapped_column(String(256))
    author_role: Mapped[str | None] = mapped_column(String(32))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sql_text("now()"), index=True
    )

    contract: Mapped[Contract] = relationship(back_populates="comments")


class DocumentTemplate(Base):
    """Шаблон документа (ТЗ, раздел 6).

    Хранит метаданные актуальности: когда проверялся на соответствие
    законодательству и кто из юристов его верифицировал.
    """

    __tablename__ = "document_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(512))
    doc_type: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    # Дата последней проверки шаблона на соответствие законодательству.
    actualized_at: Mapped[date | None] = mapped_column(Date)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    verified_by_name: Mapped[str | None] = mapped_column(String(256))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Проставляется legal_refresh, когда затронутый шаблоном НПА обновился.
    stale_reason: Mapped[str | None] = mapped_column(Text)
    stale_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="SET NULL")
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_by_name: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow
    )
