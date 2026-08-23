"""Резюме Модуля 3 у прогона проверки

ТЗ (раздел 4) требует показать юристу, «что критично поправить до подписания».
Модель это резюме возвращала, но оно нигде не сохранялось и никуда не
попадало: юрист видел список рисков без вывода.

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("review_runs", sa.Column("summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("review_runs", "summary")
