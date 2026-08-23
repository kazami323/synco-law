"""Границы пунктов в тексте документа

Правка пункта раньше пересобирала contract.content из пунктов и теряла при
этом слово «Раздел», римскую нумерацию разделов и маркеры подпунктов, а на
следующем разборе подпункты схлопывались в родителя вместе с подтверждениями
юриста. Тот же реконструированный текст уходил контрагенту в «чистом»
экспорте. С границами правка вставляется ровно на своё место.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clauses",
        sa.Column("start_offset", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "clauses",
        sa.Column("end_offset", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("clauses", "end_offset")
    op.drop_column("clauses", "start_offset")
