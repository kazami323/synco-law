"""Security sessions, server chat history and AI usage

Revision ID: 0008
Revises: 0007
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def _uuid() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("mfa_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("users", sa.Column("mfa_secret_encrypted", sa.Text(), nullable=True))

    op.create_table(
        "refresh_sessions",
        _uuid(),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])
    op.create_index("ix_refresh_sessions_token_hash", "refresh_sessions", ["token_hash"], unique=True)
    op.create_index("ix_refresh_sessions_expires_at", "refresh_sessions", ["expires_at"])

    op.create_table(
        "password_reset_tokens",
        _uuid(),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_index("ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"], unique=True)
    op.create_index("ix_password_reset_tokens_expires_at", "password_reset_tokens", ["expires_at"])

    op.create_table(
        "agent_chat_sessions",
        _uuid(),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent", sa.String(64), nullable=False),
        sa.Column("title", sa.String(256), server_default="Новый чат", nullable=False),
        sa.Column("messages", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("document_name", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_agent_chat_sessions_organization_id", "agent_chat_sessions", ["organization_id"])
    op.create_index("ix_agent_chat_sessions_user_id", "agent_chat_sessions", ["user_id"])
    op.create_index("ix_agent_chat_sessions_agent", "agent_chat_sessions", ["agent"])
    op.create_index("ix_agent_chat_sessions_contract_id", "agent_chat_sessions", ["contract_id"])
    op.create_index("ix_agent_chat_sessions_updated_at", "agent_chat_sessions", ["updated_at"])

    op.create_table(
        "ai_usage_log",
        _uuid(),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("endpoint", sa.String(128), nullable=False),
        sa.Column("agent", sa.String(64), nullable=True),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ai_usage_log_organization_id", "ai_usage_log", ["organization_id"])
    op.create_index("ix_ai_usage_log_user_id", "ai_usage_log", ["user_id"])
    op.create_index("ix_ai_usage_log_endpoint", "ai_usage_log", ["endpoint"])
    op.create_index("ix_ai_usage_log_created_at", "ai_usage_log", ["created_at"])


def downgrade() -> None:
    op.drop_table("ai_usage_log")
    op.drop_table("agent_chat_sessions")
    op.drop_table("password_reset_tokens")
    op.drop_table("refresh_sessions")
    op.drop_column("users", "mfa_secret_encrypted")
    op.drop_column("users", "mfa_enabled")
