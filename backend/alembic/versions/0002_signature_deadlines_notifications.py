"""Signature, deadlines, and notifications

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contracts", sa.Column("signature", sa.Text()))
    op.add_column(
        "contracts", sa.Column("signature_timestamp", sa.DateTime(timezone=True))
    )
    op.add_column("contracts", sa.Column("signature_certificate", sa.Text()))
    op.add_column("contracts", sa.Column("certificate_thumbprint", sa.String(128)))

    op.create_table(
        "sign_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("contract_hash", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_sign_requests_contract_id", "sign_requests", ["contract_id"])
    op.create_index("ix_sign_requests_contract_hash", "sign_requests", ["contract_hash"])

    op.create_table(
        "contract_deadlines",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("deadline_date", sa.Date(), nullable=False),
        sa.Column("type", sa.String(64), server_default="other", nullable=False),
        sa.Column("is_notified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_contract_deadlines_contract_id", "contract_deadlines", ["contract_id"]
    )
    op.create_index(
        "ix_contract_deadlines_deadline_date", "contract_deadlines", ["deadline_date"]
    )

    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="CASCADE"),
        ),
        sa.Column("text", sa.String(1024), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_contract_id", "notifications", ["contract_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("contract_deadlines")
    op.drop_table("sign_requests")
    op.drop_column("contracts", "certificate_thumbprint")
    op.drop_column("contracts", "signature_certificate")
    op.drop_column("contracts", "signature_timestamp")
    op.drop_column("contracts", "signature")
