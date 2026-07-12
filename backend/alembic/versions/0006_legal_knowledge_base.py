"""Legal knowledge base for lex.uz RAG

Revision ID: 0006
Revises: 0005
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "legal_documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source", sa.String(64), server_default="lex.uz", nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("language", sa.String(16), server_default="ru", nullable=False),
        sa.Column(
            "jurisdiction", sa.String(128), server_default="Uzbekistan", nullable=False
        ),
        sa.Column("doc_type", sa.String(64), nullable=True),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("number", sa.String(128), nullable=True),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("adopted_at", sa.Date(), nullable=True),
        sa.Column("effective_at", sa.Date(), nullable=True),
        sa.Column("current_revision_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "source", "source_id", "language", name="uq_legal_documents_source_lang"
        ),
    )
    op.create_index("ix_legal_documents_source", "legal_documents", ["source"])
    op.create_index("ix_legal_documents_source_id", "legal_documents", ["source_id"])
    op.create_index("ix_legal_documents_language", "legal_documents", ["language"])
    op.create_index("ix_legal_documents_doc_type", "legal_documents", ["doc_type"])
    op.create_index("ix_legal_documents_status", "legal_documents", ["status"])
    op.create_index(
        "ix_legal_documents_current_revision_date",
        "legal_documents",
        ["current_revision_date"],
    )

    op.create_table(
        "legal_articles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_article_id", sa.String(128), nullable=True),
        sa.Column("article_number", sa.String(64), nullable=True),
        sa.Column("title", sa.String(1024), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content_vector", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("url", sa.String(2048), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "document_id",
            "source_article_id",
            name="uq_legal_articles_source_article",
        ),
    )
    op.create_index("ix_legal_articles_document_id", "legal_articles", ["document_id"])
    op.create_index(
        "ix_legal_articles_source_article_id",
        "legal_articles",
        ["source_article_id"],
    )
    op.create_index(
        "ix_legal_articles_article_number", "legal_articles", ["article_number"]
    )
    op.create_index("ix_legal_articles_content_hash", "legal_articles", ["content_hash"])
    op.create_index("ix_legal_articles_position", "legal_articles", ["position"])
    op.execute(
        "CREATE INDEX idx_legal_articles_content_vector ON legal_articles "
        "USING ivfflat (content_vector vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_legal_articles_content_vector")
    op.drop_index("ix_legal_articles_position", table_name="legal_articles")
    op.drop_index("ix_legal_articles_content_hash", table_name="legal_articles")
    op.drop_index("ix_legal_articles_article_number", table_name="legal_articles")
    op.drop_index("ix_legal_articles_source_article_id", table_name="legal_articles")
    op.drop_index("ix_legal_articles_document_id", table_name="legal_articles")
    op.drop_table("legal_articles")

    op.drop_index(
        "ix_legal_documents_current_revision_date", table_name="legal_documents"
    )
    op.drop_index("ix_legal_documents_status", table_name="legal_documents")
    op.drop_index("ix_legal_documents_doc_type", table_name="legal_documents")
    op.drop_index("ix_legal_documents_language", table_name="legal_documents")
    op.drop_index("ix_legal_documents_source_id", table_name="legal_documents")
    op.drop_index("ix_legal_documents_source", table_name="legal_documents")
    op.drop_table("legal_documents")
