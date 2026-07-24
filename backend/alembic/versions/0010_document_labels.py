"""Отметки («плашки») на документах: кто и что с документом сделал

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_labels",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "contract_id",
            UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_agent", sa.String(64), nullable=True),
        sa.Column(
            "actor_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("actor_role", sa.String(32), nullable=True),
        sa.Column("actor_name", sa.String(256), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Плашка либо стоит, либо нет: повторная простановка обновляет автора,
        # а не плодит дубликаты.
        sa.UniqueConstraint("contract_id", "kind", name="uq_document_label_kind"),
    )
    op.create_index(
        "ix_document_labels_contract_id", "document_labels", ["contract_id"]
    )
    op.create_index("ix_document_labels_kind", "document_labels", ["kind"])
    op.create_index(
        "ix_document_labels_created_at", "document_labels", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_document_labels_created_at", table_name="document_labels")
    op.drop_index("ix_document_labels_kind", table_name="document_labels")
    op.drop_index("ix_document_labels_contract_id", table_name="document_labels")
    op.drop_table("document_labels")
