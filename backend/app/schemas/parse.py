from pydantic import Field

from app.schemas.common import AgentEnvelope, SchemaBase


class DocumentRef(SchemaBase):
    document_id: str
    file_name: str
    doc_role: str


class ParseRequest(SchemaBase):
    document_ids: list[str] = Field(default_factory=list)
    force_reparse: bool = False


class ProjectSummary(SchemaBase):
    project_name: str
    procurement_method: str
    deadline_at: str | None = None
    bid_submission_method: str = "unknown"


class DirectorySuggestionItem(SchemaBase):
    chapter_code: str
    title: str
    chapter_type: str
    mandatory_flag: bool
    evidence_refs: list[str] = Field(default_factory=list)


class StructureTemplateRequest(SchemaBase):
    template_mode: str = "basic"
    include_technical_chapter: bool | None = None
    include_appendix_chapter: bool = False
    custom_instruction: str | None = None
    replace_existing: bool = True


class StructureTemplateResult(SchemaBase):
    template_mode: str
    regenerated: bool = False
    rationale: list[str] = Field(default_factory=list)
    chapters: list[DirectorySuggestionItem] = Field(default_factory=list)


class StructureTemplateResponse(AgentEnvelope):
    result: StructureTemplateResult


class ClauseItem(SchemaBase):
    clause_code: str
    clause_category: str
    clause_title: str
    clause_text: str
    importance_level: str
    risk_level: str
    needs_response: bool
    evidence_refs: list[str] = Field(default_factory=list)


class RequirementItem(SchemaBase):
    requirement_code: str
    linked_clause_code: str
    requirement_type: str
    requirement_text: str
    response_mode: str
    acceptance_rule: str | None = None
    mandatory_flag: bool
    evidence_refs: list[str] = Field(default_factory=list)


class PricingRuleItem(SchemaBase):
    rule_code: str
    rule_text: str
    evidence_refs: list[str] = Field(default_factory=list)


class RejectionRiskItem(SchemaBase):
    risk_code: str
    severity: str
    risk_text: str
    evidence_refs: list[str] = Field(default_factory=list)


class OpenQuestionItem(SchemaBase):
    question: str
    related_document_ids: list[str] = Field(default_factory=list)


class EvidenceItem(SchemaBase):
    evidence_id: str
    document_id: str
    chunk_id: str | None = None
    page_no: int | None = None
    quote_text: str
    normalized_text: str | None = None
    evidence_type: str
    confidence_score: float | None = None


class ParseResult(SchemaBase):
    parsed_documents: list[DocumentRef] = Field(default_factory=list)
    project_summary: ProjectSummary
    directory_suggestion: list[DirectorySuggestionItem] = Field(default_factory=list)
    clauses: list[ClauseItem] = Field(default_factory=list)
    requirements: list[RequirementItem] = Field(default_factory=list)
    pricing_rules: list[PricingRuleItem] = Field(default_factory=list)
    rejection_risks: list[RejectionRiskItem] = Field(default_factory=list)
    open_questions: list[OpenQuestionItem] = Field(default_factory=list)


class ParseResponse(AgentEnvelope):
    result: ParseResult
