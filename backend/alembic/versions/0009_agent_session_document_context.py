"""Persist document context for AI chat sessions.

Revision ID: 0009
Revises: 0008
"""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_chat_sessions", sa.Column("document_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_chat_sessions", "document_text")
