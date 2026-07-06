"""organizations.compliance_policies для Compliance Agent (Phase 2)

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations", sa.Column("compliance_policies", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("organizations", "compliance_policies")
