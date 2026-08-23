"""Секрет-кандидат MFA: перенастройка не снимает действующий второй фактор

До этой миграции POST /api/auth/mfa/setup перезаписывал действующий секрет и
ставил mfa_enabled = False, ничего не спрашивая. Один запрос с угнанной сессией
снимал второй фактор и выдавал новый секрет атакующему. Теперь кандидат живёт
в отдельной колонке и становится действующим только после подтверждения кодом.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("mfa_pending_secret_encrypted", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "mfa_pending_secret_encrypted")
