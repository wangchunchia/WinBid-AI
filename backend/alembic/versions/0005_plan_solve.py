"""Add plan-and-solve tables

Revision ID: 0005_plan_solve
Revises: 0004_evidence_links
Create Date: 2026-04-26 20:40:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_plan_solve"
down_revision = "0004_evidence_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_plans",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("plan_status", sa.String(length=32), nullable=False),
        sa.Column("current_step_code", sa.String(length=64), nullable=True),
        sa.Column("overall_assessment", sa.Text(), nullable=True),
        sa.Column("blocking_reason", sa.Text(), nullable=True),
        sa.Column("requires_user_input", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_plans_project_id", "project_plans", ["project_id"], unique=False)

    op.create_table(
        "plan_steps",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("step_code", sa.String(length=64), nullable=False),
        sa.Column("step_title", sa.String(length=255), nullable=False),
        sa.Column("action_name", sa.String(length=64), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("depends_on_json", sa.Text(), nullable=True),
        sa.Column("action_payload_json", sa.Text(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("result_payload_json", sa.Text(), nullable=True),
        sa.Column("requires_user_input", sa.Boolean(), nullable=False),
        sa.Column("blocking_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_steps_plan_id", "plan_steps", ["plan_id"], unique=False)
    op.create_index("ix_plan_steps_step_code", "plan_steps", ["step_code"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_plan_steps_step_code", table_name="plan_steps")
    op.drop_index("ix_plan_steps_plan_id", table_name="plan_steps")
    op.drop_table("plan_steps")
    op.drop_index("ix_project_plans_project_id", table_name="project_plans")
    op.drop_table("project_plans")
