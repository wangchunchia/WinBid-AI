from pydantic import Field

from app.schemas.common import AgentEnvelope, SchemaBase


class RuleEngineResult(SchemaBase):
    rule_code: str
    severity: str
    status: str
    detail: str


class ComplianceCheckRequest(SchemaBase):
    include_semantic_review: bool = True
    rule_engine_results: list[RuleEngineResult] = Field(default_factory=list)


class IssueSummary(SchemaBase):
    fatal: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class ComplianceIssueItem(SchemaBase):
    issue_code: str
    issue_type: str
    severity: str
    issue_title: str
    issue_detail: str
    linked_clause_codes: list[str] = Field(default_factory=list)
    linked_material_ids: list[str] = Field(default_factory=list)
    linked_chapter_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    resolution_suggestion: str


class CoverageReport(SchemaBase):
    total_requirements: int = 0
    covered_requirements: int = 0
    uncovered_requirements: int = 0


class ComplianceResult(SchemaBase):
    overall_status: str
    issue_summary: IssueSummary
    issues: list[ComplianceIssueItem] = Field(default_factory=list)
    coverage_report: CoverageReport


class ComplianceCheckResponse(AgentEnvelope):
    result: ComplianceResult
