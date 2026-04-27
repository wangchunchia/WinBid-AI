from pydantic import Field

from app.schemas.common import AgentEnvelope, SchemaBase


class ChecklistGenerateRequest(SchemaBase):
    requirement_codes: list[str] = Field(default_factory=list)
    include_recommended: bool = True


class ChecklistItem(SchemaBase):
    material_code: str
    material_type: str
    material_name: str
    submission_category: str
    condition_expression: str | None = None
    preferred_format: str | None = None
    checklist_guidance: str
    linked_requirement_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class ChecklistSummary(SchemaBase):
    mandatory_count: int = 0
    conditional_count: int = 0
    bonus_count: int = 0
    risk_count: int = 0


class MissingEnterpriseCapability(SchemaBase):
    material_type: str
    reason: str
    condition_expression: str | None = None


class ChecklistResult(SchemaBase):
    checklist_items: list[ChecklistItem] = Field(default_factory=list)
    grouped_summary: ChecklistSummary
    missing_enterprise_capabilities: list[MissingEnterpriseCapability] = Field(default_factory=list)


class ChecklistResponse(AgentEnvelope):
    result: ChecklistResult


class MissingChecklistItem(SchemaBase):
    material_code: str
    material_type: str
    material_name: str
    submission_category: str
    reason: str
    linked_requirement_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class MissingChecklistResponse(SchemaBase):
    project_id: str
    total_required: int
    missing_count: int
    missing_items: list[MissingChecklistItem] = Field(default_factory=list)
