"""Add chat memory tables

Revision ID: 0006_chat_memory
Revises: 0005_plan_solve
Create Date: 2026-04-26 22:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_chat_memory"
down_revision = "0005_plan_solve"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_chat_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("session_status", sa.String(length=32), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("last_agent_action", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_chat_sessions_project_id", "project_chat_sessions", ["project_id"], unique=False)

    op.create_table(
        "project_chat_messages",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=64), nullable=True),
        sa.Column("related_action", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_chat_messages_project_id", "project_chat_messages", ["project_id"], unique=False)
    op.create_index("ix_project_chat_messages_session_id", "project_chat_messages", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_project_chat_messages_session_id", table_name="project_chat_messages")
    op.drop_index("ix_project_chat_messages_project_id", table_name="project_chat_messages")
    op.drop_table("project_chat_messages")
    op.drop_index("ix_project_chat_sessions_project_id", table_name="project_chat_sessions")
    op.drop_table("project_chat_sessions")
