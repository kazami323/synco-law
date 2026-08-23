"""Правовой движок: пункты, вердикты, решения юриста, находки, шаблоны

Реализует ТЗ «Правовой движок»: разделы 1 (контекст и участники проекта),
4 (работа по пунктам, Модули 1-3), 6 (база шаблонов), 7 (комментарии).

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def _id_column():
    return sa.Column(
        "id",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _created_at():
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _updated_at():
    return sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def upgrade() -> None:
    # --- Проект: общий контекст и участники (ТЗ, раздел 1) ---
    op.add_column("projects", sa.Column("context", JSONB(), nullable=True))

    op.create_table(
        "project_members",
        _id_column(),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("access", sa.String(16), server_default="write", nullable=False),
        sa.Column("added_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        _created_at(),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_member"),
    )
    op.create_index("ix_project_members_project_id", "project_members", ["project_id"])
    op.create_index("ix_project_members_user_id", "project_members", ["user_id"])

    # --- Пункты документа (ТЗ, раздел 4, Модуль 1) ---
    op.create_table(
        "clauses",
        _id_column(),
        sa.Column(
            "contract_id",
            UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clauses.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("anchor", sa.String(64), nullable=False),
        sa.Column("number", sa.String(64), nullable=True),
        sa.Column("level", sa.Integer(), server_default="1", nullable=False),
        sa.Column("title", sa.String(1024), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        _created_at(),
        _updated_at(),
        sa.UniqueConstraint("contract_id", "anchor", name="uq_clause_anchor"),
    )
    op.create_index("ix_clauses_contract_id", "clauses", ["contract_id"])
    op.create_index("ix_clauses_parent_id", "clauses", ["parent_id"])
    op.create_index("ix_clauses_anchor", "clauses", ["anchor"])
    op.create_index("ix_clauses_content_hash", "clauses", ["content_hash"])
    op.create_index("ix_clauses_position", "clauses", ["position"])

    # --- Прогоны модулей проверки ---
    op.create_table(
        "review_runs",
        _id_column(),
        sa.Column(
            "contract_id",
            UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("module", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), server_default="running", nullable=False),
        sa.Column("party_side", sa.String(256), nullable=True),
        sa.Column("clauses_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("findings_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_review_runs_contract_id", "review_runs", ["contract_id"])
    op.create_index("ix_review_runs_module", "review_runs", ["module"])
    op.create_index("ix_review_runs_status", "review_runs", ["status"])
    op.create_index("ix_review_runs_started_at", "review_runs", ["started_at"])

    # --- Сверка пункта с нормой ---
    op.create_table(
        "clause_checks",
        _id_column(),
        sa.Column(
            "clause_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clauses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("review_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("suggested_text", sa.Text(), nullable=True),
        # Снапшот норм на дату проверки: ТЗ требует воспроизводимости
        # результата после обновления законодательства.
        sa.Column("sources", JSONB(), nullable=True),
        sa.Column(
            "checked_on",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),
        _created_at(),
    )
    op.create_index("ix_clause_checks_clause_id", "clause_checks", ["clause_id"])
    op.create_index("ix_clause_checks_run_id", "clause_checks", ["run_id"])
    op.create_index("ix_clause_checks_verdict", "clause_checks", ["verdict"])
    op.create_index("ix_clause_checks_created_at", "clause_checks", ["created_at"])

    # --- Решения юриста по пунктам ---
    op.create_table(
        "clause_decisions",
        _id_column(),
        sa.Column(
            "clause_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clauses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("previous_text", sa.Text(), nullable=True),
        sa.Column("new_text", sa.Text(), nullable=True),
        sa.Column("clause_hash", sa.String(64), nullable=True),
        sa.Column(
            "is_current", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("decided_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_by_name", sa.String(256), nullable=True),
        _created_at(),
    )
    op.create_index("ix_clause_decisions_clause_id", "clause_decisions", ["clause_id"])
    op.create_index("ix_clause_decisions_action", "clause_decisions", ["action"])
    op.create_index("ix_clause_decisions_is_current", "clause_decisions", ["is_current"])
    op.create_index("ix_clause_decisions_created_at", "clause_decisions", ["created_at"])

    # --- Находки Модуля 2 ---
    op.create_table(
        "logic_findings",
        _id_column(),
        sa.Column(
            "contract_id",
            UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("review_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=True),
        sa.Column("clause_anchors", JSONB(), nullable=True),
        sa.Column("detected_by", sa.String(16), server_default="rule", nullable=False),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
    )
    op.create_index("ix_logic_findings_contract_id", "logic_findings", ["contract_id"])
    op.create_index("ix_logic_findings_run_id", "logic_findings", ["run_id"])
    op.create_index("ix_logic_findings_category", "logic_findings", ["category"])
    op.create_index("ix_logic_findings_status", "logic_findings", ["status"])
    op.create_index("ix_logic_findings_created_at", "logic_findings", ["created_at"])

    # --- Находки Модуля 3 ---
    op.create_table(
        "risk_findings",
        _id_column(),
        sa.Column(
            "contract_id",
            UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("review_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("consequence", sa.Text(), nullable=True),
        sa.Column("mitigation", sa.Text(), nullable=True),
        sa.Column("clause_anchors", JSONB(), nullable=True),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column("resolved_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
    )
    op.create_index("ix_risk_findings_contract_id", "risk_findings", ["contract_id"])
    op.create_index("ix_risk_findings_run_id", "risk_findings", ["run_id"])
    op.create_index("ix_risk_findings_category", "risk_findings", ["category"])
    op.create_index("ix_risk_findings_level", "risk_findings", ["level"])
    op.create_index("ix_risk_findings_status", "risk_findings", ["status"])
    op.create_index("ix_risk_findings_created_at", "risk_findings", ["created_at"])

    # --- Комментарии (роль «Наблюдатель», ТЗ раздел 7) ---
    op.create_table(
        "document_comments",
        _id_column(),
        sa.Column(
            "contract_id",
            UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "clause_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clauses.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("author_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("author_name", sa.String(256), nullable=True),
        sa.Column("author_role", sa.String(32), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
    )
    op.create_index("ix_document_comments_contract_id", "document_comments", ["contract_id"])
    op.create_index("ix_document_comments_clause_id", "document_comments", ["clause_id"])
    op.create_index("ix_document_comments_created_at", "document_comments", ["created_at"])

    # --- База шаблонов (ТЗ, раздел 6) ---
    op.create_table(
        "document_templates",
        _id_column(),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("doc_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("actualized_at", sa.Date(), nullable=True),
        sa.Column("verified_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("verified_by_name", sa.String(256), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stale_reason", sa.Text(), nullable=True),
        sa.Column("stale_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "source_contract_id",
            UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "is_archived", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by_name", sa.String(256), nullable=True),
        _created_at(),
        _updated_at(),
    )
    op.create_index(
        "ix_document_templates_organization_id", "document_templates", ["organization_id"]
    )
    op.create_index("ix_document_templates_doc_type", "document_templates", ["doc_type"])
    op.create_index(
        "ix_document_templates_is_archived", "document_templates", ["is_archived"]
    )
    op.create_index(
        "ix_document_templates_created_at", "document_templates", ["created_at"]
    )


def downgrade() -> None:
    op.drop_table("document_templates")
    op.drop_table("document_comments")
    op.drop_table("risk_findings")
    op.drop_table("logic_findings")
    op.drop_table("clause_decisions")
    op.drop_table("clause_checks")
    op.drop_table("review_runs")
    op.drop_table("clauses")
    op.drop_table("project_members")
    op.drop_column("projects", "context")
