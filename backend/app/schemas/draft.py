from pydantic import Field

from app.schemas.common import AgentEnvelope, SchemaBase


class DraftGenerateRequest(SchemaBase):
    chapter_codes: list[str] = Field(default_factory=list)
    regenerate_existing: bool = False


class DraftSectionItem(SchemaBase):
    section_title: str
    section_order: int
    generated_text: str
    linked_requirement_codes: list[str] = Field(default_factory=list)
    linked_material_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)


class ChapterSummary(SchemaBase):
    generated_section_count: int = 0
    pending_section_count: int = 0


class DraftResult(SchemaBase):
    chapter_code: str
    chapter_title: str | None = None
    chapter_type: str | None = None
    draft_sections: list[DraftSectionItem] = Field(default_factory=list)
    chapter_summary: ChapterSummary


class DraftGenerateResponse(AgentEnvelope):
    result: DraftResult


class DraftChapterView(SchemaBase):
    chapter_code: str
    chapter_title: str
    chapter_type: str
    generation_status: str
    draft_sections: list[DraftSectionItem] = Field(default_factory=list)
    chapter_summary: ChapterSummary
