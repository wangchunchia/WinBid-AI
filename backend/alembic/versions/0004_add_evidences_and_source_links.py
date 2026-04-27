"""Add evidences and source links

Revision ID: 0004_evidence_links
Revises: 0003_add_document_chunks
Create Date: 2026-04-26 18:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_evidence_links"
down_revision = "0003_add_document_chunks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidences",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("chunk_id", sa.String(length=64), nullable=True),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("quote_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=True),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidences_chunk_id", "evidences", ["chunk_id"], unique=False)
    op.create_index("ix_evidences_document_id", "evidences", ["document_id"], unique=False)
    op.create_index("ix_evidences_project_id", "evidences", ["project_id"], unique=False)

    op.add_column("requirements", sa.Column("source_evidence_id", sa.String(length=64), nullable=True))
    op.add_column("pricing_rules", sa.Column("source_evidence_id", sa.String(length=64), nullable=True))
    op.add_column("rejection_risks", sa.Column("source_evidence_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("rejection_risks", "source_evidence_id")
    op.drop_column("pricing_rules", "source_evidence_id")
    op.drop_column("requirements", "source_evidence_id")
    op.drop_index("ix_evidences_project_id", table_name="evidences")
    op.drop_index("ix_evidences_document_id", table_name="evidences")
    op.drop_index("ix_evidences_chunk_id", table_name="evidences")
    op.drop_table("evidences")
