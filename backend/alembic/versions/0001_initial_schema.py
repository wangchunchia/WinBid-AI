"""Initial schema

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-04-26 16:50:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=True),
        sa.Column("output_json", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("run_status", sa.String(length=32), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_project_id", "agent_runs", ["project_id"], unique=False)

    op.create_table(
        "chapters",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("chapter_code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("chapter_order", sa.Integer(), nullable=False),
        sa.Column("chapter_type", sa.String(length=64), nullable=False),
        sa.Column("generation_status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chapters_chapter_code", "chapters", ["chapter_code"], unique=False)
    op.create_index("ix_chapters_project_id", "chapters", ["project_id"], unique=False)

    op.create_table(
        "clauses",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("clause_code", sa.String(length=64), nullable=False),
        sa.Column("clause_category", sa.String(length=64), nullable=False),
        sa.Column("clause_title", sa.String(length=255), nullable=False),
        sa.Column("clause_text", sa.Text(), nullable=False),
        sa.Column("source_evidence_id", sa.String(length=64), nullable=True),
        sa.Column("importance_level", sa.String(length=32), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("needs_response", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clauses_clause_code", "clauses", ["clause_code"], unique=False)
    op.create_index("ix_clauses_project_id", "clauses", ["project_id"], unique=False)

    op.create_table(
        "compliance_issues",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("issue_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("issue_title", sa.String(length=255), nullable=False),
        sa.Column("issue_detail", sa.Text(), nullable=False),
        sa.Column("linked_clause_id", sa.String(length=64), nullable=True),
        sa.Column("linked_material_id", sa.String(length=64), nullable=True),
        sa.Column("linked_chapter_id", sa.String(length=64), nullable=True),
        sa.Column("resolution_suggestion", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_compliance_issues_project_id", "compliance_issues", ["project_id"], unique=False)

    op.create_table(
        "draft_sections",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("chapter_id", sa.String(length=64), nullable=False),
        sa.Column("section_title", sa.String(length=255), nullable=False),
        sa.Column("section_order", sa.Integer(), nullable=False),
        sa.Column("generated_text", sa.Text(), nullable=False),
        sa.Column("source_summary_json", sa.Text(), nullable=True),
        sa.Column("missing_info_json", sa.Text(), nullable=True),
        sa.Column("generation_status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_draft_sections_chapter_id", "draft_sections", ["chapter_id"], unique=False)

    op.create_table(
        "material_requirements",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("requirement_id", sa.String(length=64), nullable=False),
        sa.Column("material_type", sa.String(length=64), nullable=False),
        sa.Column("material_name", sa.String(length=255), nullable=False),
        sa.Column("submission_category", sa.String(length=32), nullable=False),
        sa.Column("condition_expression", sa.Text(), nullable=True),
        sa.Column("preferred_format", sa.String(length=32), nullable=True),
        sa.Column("checklist_guidance", sa.Text(), nullable=True),
        sa.Column("alternative_allowed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_material_requirements_project_id", "material_requirements", ["project_id"], unique=False)
    op.create_index("ix_material_requirements_requirement_id", "material_requirements", ["requirement_id"], unique=False)

    op.create_table(
        "requirements",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("clause_id", sa.String(length=64), nullable=False),
        sa.Column("requirement_type", sa.String(length=64), nullable=False),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column("response_mode", sa.String(length=64), nullable=False),
        sa.Column("acceptance_rule", sa.Text(), nullable=True),
        sa.Column("mandatory_flag", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_requirements_clause_id", "requirements", ["clause_id"], unique=False)

    op.create_table(
        "source_documents",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=64), nullable=False),
        sa.Column("doc_role", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.String(length=512), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("parse_status", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_documents_project_id", "source_documents", ["project_id"], unique=False)

    op.create_table(
        "tender_projects",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_code", sa.String(length=64), nullable=False),
        sa.Column("project_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("bidder_company_id", sa.String(length=64), nullable=True),
        sa.Column("deadline_at", sa.DateTime(), nullable=True),
        sa.Column("procurement_method", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tender_projects_project_code", "tender_projects", ["project_code"], unique=True)
    op.create_index("ix_tender_projects_project_name", "tender_projects", ["project_name"], unique=False)

    op.create_table(
        "user_materials",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("material_requirement_id", sa.String(length=64), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("material_type", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.String(length=512), nullable=False),
        sa.Column("review_status", sa.String(length=64), nullable=False),
        sa.Column("matched_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_materials_project_id", "user_materials", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_materials_project_id", table_name="user_materials")
    op.drop_table("user_materials")
    op.drop_index("ix_tender_projects_project_name", table_name="tender_projects")
    op.drop_index("ix_tender_projects_project_code", table_name="tender_projects")
    op.drop_table("tender_projects")
    op.drop_index("ix_source_documents_project_id", table_name="source_documents")
    op.drop_table("source_documents")
    op.drop_index("ix_requirements_clause_id", table_name="requirements")
    op.drop_table("requirements")
    op.drop_index("ix_material_requirements_requirement_id", table_name="material_requirements")
    op.drop_index("ix_material_requirements_project_id", table_name="material_requirements")
    op.drop_table("material_requirements")
    op.drop_index("ix_draft_sections_chapter_id", table_name="draft_sections")
    op.drop_table("draft_sections")
    op.drop_index("ix_compliance_issues_project_id", table_name="compliance_issues")
    op.drop_table("compliance_issues")
    op.drop_index("ix_clauses_project_id", table_name="clauses")
    op.drop_index("ix_clauses_clause_code", table_name="clauses")
    op.drop_table("clauses")
    op.drop_index("ix_chapters_project_id", table_name="chapters")
    op.drop_index("ix_chapters_chapter_code", table_name="chapters")
    op.drop_table("chapters")
    op.drop_index("ix_agent_runs_project_id", table_name="agent_runs")
    op.drop_table("agent_runs")
