"""Initial schema: organizations, users, contracts, versions, agent_results, workflow, audit

Revision ID: 0001
Revises:
Create Date: 2026-07-04

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("phone", sa.String(64)),
        sa.Column("address", sa.String(1024)),
        sa.Column("country", sa.String(128), server_default="Uzbekistan", nullable=False),
        sa.Column("storage_limit", sa.Integer(), server_default="1000", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("username", sa.String(128), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(256)),
        sa.Column("role", sa.String(32), server_default="lawyer", nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id")),
        sa.Column("department_id", postgresql.UUID(as_uuid=True)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "contracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id")),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("contract_type", sa.String(64)),
        sa.Column("counterparty", sa.String(512)),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("content", sa.Text()),
        sa.Column("file_path", sa.String(1024)),
        sa.Column("content_vector", Vector(EMBEDDING_DIM)),
        sa.Column("amount", sa.Numeric(18, 2)),
        sa.Column("currency", sa.String(8), server_default="UZS", nullable=False),
        sa.Column("risk_score", sa.Integer()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True)),
        sa.Column("signed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
    )
    op.create_index("idx_contracts_organization", "contracts", ["organization_id"])
    op.create_index("idx_contracts_status", "contracts", ["status"])
    op.create_index("idx_contracts_created_at", "contracts", ["created_at"])
    op.execute(
        "CREATE INDEX idx_contracts_content_vector ON contracts "
        "USING ivfflat (content_vector vector_cosine_ops)"
    )

    op.create_table(
        "contract_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text()),
        sa.Column("changes_description", sa.String(1024)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_contract_versions_contract_id", "contract_versions", ["contract_id"])

    op.create_table(
        "agent_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("result_type", sa.String(64)),
        sa.Column("result_data", postgresql.JSONB()),
        sa.Column("confidence_score", sa.Float()),
        sa.Column("execution_time_ms", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_agent_results_contract", "agent_results", ["contract_id"])

    op.create_table(
        "workflow_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("current_stage", sa.String(64), nullable=False),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("comments", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_workflow_states_contract_id", "workflow_states", ["contract_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64)),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("changes", postgresql.JSONB()),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_audit_log_user", "audit_log", ["user_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("workflow_states")
    op.drop_table("agent_results")
    op.drop_table("contract_versions")
    op.drop_table("contracts")
    op.drop_table("users")
    op.drop_table("organizations")
    op.execute("DROP EXTENSION IF EXISTS vector")
