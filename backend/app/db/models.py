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
    EXTERNAL = "external"


class ContractStatus(str, enum.Enum):
    DRAFT = "draft"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    APPROVED = "approved"
    APPROVED_FINANCE = "approved_finance"
    READY_TO_SIGN = "ready_to_sign"
    SIGNED = "signed"
    ARCHIVED = "archived"


class ContractType(str, enum.Enum):
    PURCHASE = "purchase"
    LEASE = "lease"
    SERVICE = "service"
    NDA = "nda"
    EMPLOYMENT = "employment"
    OTHER = "other"


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
