"""Хеш текста пункта у вердикта Модуля 1

Без него вердикт не устаревал вместе с текстом: юрист правил пункт и
продолжал видеть «соответствует», вынесенное по прежней редакции. У решения
юриста такой хеш был с самого начала (clause_decisions.clause_hash).

Существующие вердикты остаются с NULL: про них честно неизвестно, к какой
редакции они относятся, и помечать их устаревшими задним числом было бы
такой же выдумкой, как считать актуальными.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clause_checks", sa.Column("clause_hash", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("clause_checks", "clause_hash")
