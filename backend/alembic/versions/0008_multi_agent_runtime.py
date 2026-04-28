"""Add multi-agent runtime tables

Revision ID: 0008_multi_agent_runtime
Revises: 0007_project_memory
Create Date: 2026-04-27 10:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_multi_agent_runtime"
down_revision = "0007_project_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("parent_task_id", sa.String(length=64), nullable=True),
        sa.Column("depends_on_task_id", sa.String(length=64), nullable=True),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("assigned_by", sa.String(length=64), nullable=True),
        sa.Column("input_json", sa.Text(), nullable=True),
        sa.Column("output_json", sa.Text(), nullable=True),
        sa.Column("task_status", sa.String(length=32), nullable=False),
        sa.Column("blocking_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_tasks_agent_name", "agent_tasks", ["agent_name"], unique=False)
    op.create_index("ix_agent_tasks_depends_on_task_id", "agent_tasks", ["depends_on_task_id"], unique=False)
    op.create_index("ix_agent_tasks_parent_task_id", "agent_tasks", ["parent_task_id"], unique=False)
    op.create_index("ix_agent_tasks_project_id", "agent_tasks", ["project_id"], unique=False)
    op.create_index("ix_agent_tasks_session_id", "agent_tasks", ["session_id"], unique=False)
    op.create_index("ix_agent_tasks_task_type", "agent_tasks", ["task_type"], unique=False)

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("from_agent", sa.String(length=64), nullable=False),
        sa.Column("to_agent", sa.String(length=64), nullable=False),
        sa.Column("message_type", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("delivery_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_messages_from_agent", "agent_messages", ["from_agent"], unique=False)
    op.create_index("ix_agent_messages_message_type", "agent_messages", ["message_type"], unique=False)
    op.create_index("ix_agent_messages_project_id", "agent_messages", ["project_id"], unique=False)
    op.create_index("ix_agent_messages_session_id", "agent_messages", ["session_id"], unique=False)
    op.create_index("ix_agent_messages_task_id", "agent_messages", ["task_id"], unique=False)
    op.create_index("ix_agent_messages_to_agent", "agent_messages", ["to_agent"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_messages_to_agent", table_name="agent_messages")
    op.drop_index("ix_agent_messages_task_id", table_name="agent_messages")
    op.drop_index("ix_agent_messages_session_id", table_name="agent_messages")
    op.drop_index("ix_agent_messages_project_id", table_name="agent_messages")
    op.drop_index("ix_agent_messages_message_type", table_name="agent_messages")
    op.drop_index("ix_agent_messages_from_agent", table_name="agent_messages")
    op.drop_table("agent_messages")

    op.drop_index("ix_agent_tasks_task_type", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_session_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_project_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_parent_task_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_depends_on_task_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_agent_name", table_name="agent_tasks")
    op.drop_table("agent_tasks")
