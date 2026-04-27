"""Add project memory items

Revision ID: 0007_project_memory
Revises: 0006_chat_memory
Create Date: 2026-04-26 22:55:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_project_memory"
down_revision = "0006_chat_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_memory_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("memory_type", sa.String(length=64), nullable=False),
        sa.Column("memory_key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags_json", sa.Text(), nullable=True),
        sa.Column("source_message_id", sa.String(length=64), nullable=True),
        sa.Column("importance_score", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_memory_items_memory_key", "project_memory_items", ["memory_key"], unique=False)
    op.create_index("ix_project_memory_items_memory_type", "project_memory_items", ["memory_type"], unique=False)
    op.create_index("ix_project_memory_items_project_id", "project_memory_items", ["project_id"], unique=False)
    op.create_index("ix_project_memory_items_session_id", "project_memory_items", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_project_memory_items_session_id", table_name="project_memory_items")
    op.drop_index("ix_project_memory_items_project_id", table_name="project_memory_items")
    op.drop_index("ix_project_memory_items_memory_type", table_name="project_memory_items")
    op.drop_index("ix_project_memory_items_memory_key", table_name="project_memory_items")
    op.drop_table("project_memory_items")
