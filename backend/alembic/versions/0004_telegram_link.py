"""users.telegram_chat_id / telegram_link_code для Telegram-уведомлений

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_chat_id", sa.String(64), nullable=True))
    op.add_column(
        "users", sa.Column("telegram_link_code", sa.String(64), nullable=True)
    )
    op.create_index(
        "ix_users_telegram_link_code", "users", ["telegram_link_code"]
    )


def downgrade() -> None:
    op.drop_index("ix_users_telegram_link_code", table_name="users")
    op.drop_column("users", "telegram_link_code")
    op.drop_column("users", "telegram_chat_id")
