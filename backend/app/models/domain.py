from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TenderProject(Base, TimestampMixin):
    __tablename__ = "tender_projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    project_name: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(64), default="created")
    bidder_company_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    procurement_method: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SourceDocument(Base, TimestampMixin):
    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(64))
    doc_role: Mapped[str] = mapped_column(String(64))
    storage_uri: Mapped[str] = mapped_column(String(512))
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parse_status: Mapped[str] = mapped_column(String(64), default="pending")
    uploaded_by: Mapped[str] = mapped_column(String(64), default="user")


class DocumentChunk(Base, TimestampMixin):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    page_no: Mapped[int] = mapped_column(Integer)
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_type: Mapped[str] = mapped_column(String(32), default="paragraph")
    text_content: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer, default=0)


class Evidence(Base, TimestampMixin):
    __tablename__ = "evidences"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    chunk_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote_text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(32), default="clause")
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)


class Clause(Base, TimestampMixin):
    __tablename__ = "clauses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    clause_code: Mapped[str] = mapped_column(String(64), index=True)
    clause_category: Mapped[str] = mapped_column(String(64))
    clause_title: Mapped[str] = mapped_column(String(255))
    clause_text: Mapped[str] = mapped_column(Text)
    source_evidence_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    importance_level: Mapped[str] = mapped_column(String(32))
    risk_level: Mapped[str] = mapped_column(String(32))
    needs_response: Mapped[bool] = mapped_column(Boolean, default=True)


class Requirement(Base, TimestampMixin):
    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    clause_id: Mapped[str] = mapped_column(String(64), index=True)
    requirement_type: Mapped[str] = mapped_column(String(64))
    requirement_text: Mapped[str] = mapped_column(Text)
    response_mode: Mapped[str] = mapped_column(String(64))
    acceptance_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_evidence_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mandatory_flag: Mapped[bool] = mapped_column(Boolean, default=True)


class PricingRule(Base, TimestampMixin):
    __tablename__ = "pricing_rules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    rule_code: Mapped[str] = mapped_column(String(64), index=True)
    rule_text: Mapped[str] = mapped_column(Text)
    source_evidence_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class RejectionRisk(Base, TimestampMixin):
    __tablename__ = "rejection_risks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    risk_code: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(32))
    risk_text: Mapped[str] = mapped_column(Text)
    source_evidence_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ParseOpenQuestion(Base, TimestampMixin):
    __tablename__ = "parse_open_questions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text)
    related_document_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class MaterialRequirement(Base, TimestampMixin):
    __tablename__ = "material_requirements"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    requirement_id: Mapped[str] = mapped_column(String(64), index=True)
    material_type: Mapped[str] = mapped_column(String(64))
    material_name: Mapped[str] = mapped_column(String(255))
    submission_category: Mapped[str] = mapped_column(String(32))
    condition_expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    checklist_guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    alternative_allowed: Mapped[bool] = mapped_column(Boolean, default=False)


class UserMaterial(Base, TimestampMixin):
    __tablename__ = "user_materials"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    material_requirement_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255))
    material_type: Mapped[str] = mapped_column(String(64))
    storage_uri: Mapped[str] = mapped_column(String(512))
    review_status: Mapped[str] = mapped_column(String(64), default="uploaded")
    matched_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)


class Chapter(Base, TimestampMixin):
    __tablename__ = "chapters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    chapter_code: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    chapter_order: Mapped[int] = mapped_column(Integer)
    chapter_type: Mapped[str] = mapped_column(String(64))
    generation_status: Mapped[str] = mapped_column(String(64), default="pending")


class DraftSection(Base, TimestampMixin):
    __tablename__ = "draft_sections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chapter_id: Mapped[str] = mapped_column(String(64), index=True)
    section_title: Mapped[str] = mapped_column(String(255))
    section_order: Mapped[int] = mapped_column(Integer)
    generated_text: Mapped[str] = mapped_column(Text)
    source_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_info_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_status: Mapped[str] = mapped_column(String(64), default="draft")


class ComplianceIssue(Base, TimestampMixin):
    __tablename__ = "compliance_issues"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    issue_type: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(32))
    issue_title: Mapped[str] = mapped_column(String(255))
    issue_detail: Mapped[str] = mapped_column(Text)
    linked_clause_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    linked_material_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    linked_chapter_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolution_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open")


class ProjectPlan(Base, TimestampMixin):
    __tablename__ = "project_plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    goal: Mapped[str] = mapped_column(Text)
    plan_status: Mapped[str] = mapped_column(String(32), default="in_progress")
    current_step_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    overall_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocking_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_user_input: Mapped[bool] = mapped_column(Boolean, default=False)


class PlanStep(Base, TimestampMixin):
    __tablename__ = "plan_steps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(64), index=True)
    step_code: Mapped[str] = mapped_column(String(64), index=True)
    step_title: Mapped[str] = mapped_column(String(255))
    action_name: Mapped[str] = mapped_column(String(64))
    step_order: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    depends_on_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_user_input: Mapped[bool] = mapped_column(Boolean, default=False)
    blocking_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProjectChatSession(Base, TimestampMixin):
    __tablename__ = "project_chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255), default="项目对话")
    session_status: Mapped[str] = mapped_column(String(32), default="active")
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_agent_action: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ProjectChatMessage(Base, TimestampMixin):
    __tablename__ = "project_chat_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    related_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProjectMemoryItem(Base, TimestampMixin):
    __tablename__ = "project_memory_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    memory_type: Mapped[str] = mapped_column(String(64), index=True)
    memory_key: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    importance_score: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="active")


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_name: Mapped[str] = mapped_column(String(64))
    input_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    run_status: Mapped[str] = mapped_column(String(32), default="success")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
