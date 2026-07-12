"""Organization invite codes

Revision ID: 0007
Revises: 0006
"""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("invite_code", sa.String(32)))
    op.execute(
        """
        UPDATE organizations
        SET invite_code = upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 10))
        WHERE invite_code IS NULL
        """
    )
    op.alter_column("organizations", "invite_code", nullable=False)
    op.create_index(
        "ix_organizations_invite_code",
        "organizations",
        ["invite_code"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_organizations_invite_code", table_name="organizations")
    op.drop_column("organizations", "invite_code")
