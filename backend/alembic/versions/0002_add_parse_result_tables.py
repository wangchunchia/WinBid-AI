"""Add parse result tables

Revision ID: 0002_add_parse_result_tables
Revises: 0001_initial_schema
Create Date: 2026-04-26 17:15:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_parse_result_tables"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parse_open_questions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("related_document_ids_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_parse_open_questions_project_id", "parse_open_questions", ["project_id"], unique=False)

    op.create_table(
        "pricing_rules",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("rule_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pricing_rules_project_id", "pricing_rules", ["project_id"], unique=False)
    op.create_index("ix_pricing_rules_rule_code", "pricing_rules", ["rule_code"], unique=False)

    op.create_table(
        "rejection_risks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("risk_code", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("risk_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rejection_risks_project_id", "rejection_risks", ["project_id"], unique=False)
    op.create_index("ix_rejection_risks_risk_code", "rejection_risks", ["risk_code"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_rejection_risks_risk_code", table_name="rejection_risks")
    op.drop_index("ix_rejection_risks_project_id", table_name="rejection_risks")
    op.drop_table("rejection_risks")
    op.drop_index("ix_pricing_rules_rule_code", table_name="pricing_rules")
    op.drop_index("ix_pricing_rules_project_id", table_name="pricing_rules")
    op.drop_table("pricing_rules")
    op.drop_index("ix_parse_open_questions_project_id", table_name="parse_open_questions")
    op.drop_table("parse_open_questions")
