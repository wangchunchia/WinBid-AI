import json
from collections import defaultdict
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.domain import Chapter, Clause, DraftSection, MaterialRequirement, Requirement, TenderProject, UserMaterial
from app.schemas.draft import ChapterSummary, DraftChapterView, DraftGenerateRequest, DraftGenerateResponse, DraftResult, DraftSectionItem
from app.services.llm_draft_service import LlmDraftContext, llm_draft_service


class DraftService:
    def generate_draft(self, db: Session, project_id: str, payload: DraftGenerateRequest) -> DraftGenerateResponse:
        chapters = self._load_target_chapters(db, project_id, payload.chapter_codes)
        if not chapters:
            raise ValueError("No draftable chapters found for this project")

        chapter = chapters[0]
        if payload.regenerate_existing:
            db.execute(delete(DraftSection).where(DraftSection.chapter_id == chapter.id))

        requirements_map = self._load_requirements_by_category(db, project_id)
        checklist_rows = self._load_checklist_rows(db, project_id)
        uploaded_materials = db.scalars(
            select(UserMaterial).where(UserMaterial.project_id == project_id).order_by(UserMaterial.created_at.desc())
        ).all()

        draft_sections = self._build_chapter_sections(
            chapter=chapter,
            requirements_map=requirements_map,
            checklist_rows=checklist_rows,
            uploaded_materials=uploaded_materials,
        )
        draft_sections = self._enhance_sections_with_llm(
            chapter=chapter,
            draft_sections=draft_sections,
            requirements_map=requirements_map,
            checklist_rows=checklist_rows,
            uploaded_materials=uploaded_materials,
        )
        self._persist_sections(db, chapter, draft_sections)
        chapter.generation_status = "generated"
        project = db.get(TenderProject, project_id)
        if project:
            project.status = "draft_generated"
        db.commit()

        summary = ChapterSummary(
            generated_section_count=sum(1 for item in draft_sections if item.generated_text.strip()),
            pending_section_count=sum(1 for item in draft_sections if item.missing_info),
        )
        return DraftGenerateResponse(
            run_id=str(uuid4()),
            agent_name="bid_generation_agent",
            project_id=project_id,
            status="success",
            warnings=["Only the first requested chapter was generated in this MVP run."] if len(chapters) > 1 else [],
            errors=[],
            result=DraftResult(
                chapter_code=chapter.chapter_code,
                chapter_title=chapter.title,
                chapter_type=chapter.chapter_type,
                draft_sections=draft_sections,
                chapter_summary=summary,
            ),
        )

    def list_drafts(self, db: Session, project_id: str) -> list[DraftChapterView]:
        chapters = db.scalars(
            select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_order.asc(), Chapter.created_at.asc())
        ).all()
        chapter_ids = [chapter.id for chapter in chapters]
        if not chapter_ids:
            return []
        rows = db.scalars(
            select(DraftSection)
            .where(DraftSection.chapter_id.in_(chapter_ids))
            .order_by(DraftSection.section_order.asc(), DraftSection.created_at.asc())
        ).all()
        sections_by_chapter: dict[str, list[DraftSection]] = defaultdict(list)
        for row in rows:
            sections_by_chapter[row.chapter_id].append(row)

        result: list[DraftChapterView] = []
        for chapter in chapters:
            sections = [self._to_section_item(section) for section in sections_by_chapter.get(chapter.id, [])]
            result.append(
                DraftChapterView(
                    chapter_code=chapter.chapter_code,
                    chapter_title=chapter.title,
                    chapter_type=chapter.chapter_type,
                    generation_status=chapter.generation_status,
                    draft_sections=sections,
                    chapter_summary=ChapterSummary(
                        generated_section_count=sum(1 for item in sections if item.generated_text.strip()),
                        pending_section_count=sum(1 for item in sections if item.missing_info),
                    ),
                )
            )
        return result

    def _load_target_chapters(self, db: Session, project_id: str, chapter_codes: list[str]) -> list[Chapter]:
        stmt = select(Chapter).where(Chapter.project_id == project_id)
        if chapter_codes:
            stmt = stmt.where(Chapter.chapter_code.in_(chapter_codes))
        else:
            stmt = stmt.where(Chapter.chapter_type.in_(["qualification", "commercial", "pricing"]))
        return db.scalars(stmt.order_by(Chapter.chapter_order.asc(), Chapter.created_at.asc())).all()

    def _load_requirements_by_category(self, db: Session, project_id: str) -> dict[str, list[tuple[Requirement, Clause]]]:
        rows = db.execute(
            select(Requirement, Clause)
            .join(Clause, Requirement.clause_id == Clause.id)
            .where(Clause.project_id == project_id)
            .order_by(Requirement.created_at.asc())
        ).all()
        mapping: dict[str, list[tuple[Requirement, Clause]]] = defaultdict(list)
        for requirement, clause in rows:
            mapping[clause.clause_category].append((requirement, clause))
        return mapping

    def _load_checklist_rows(
        self,
        db: Session,
        project_id: str,
    ) -> list[tuple[MaterialRequirement, Requirement, Clause]]:
        return list(
            db.execute(
                select(MaterialRequirement, Requirement, Clause)
                .join(Requirement, MaterialRequirement.requirement_id == Requirement.id)
                .join(Clause, Requirement.clause_id == Clause.id)
                .where(MaterialRequirement.project_id == project_id)
                .order_by(MaterialRequirement.created_at.asc())
            ).all()
        )

    def _build_chapter_sections(
        self,
        chapter: Chapter,
        requirements_map: dict[str, list[tuple[Requirement, Clause]]],
        checklist_rows: list[tuple[MaterialRequirement, Requirement, Clause]],
        uploaded_materials: list[UserMaterial],
    ) -> list[DraftSectionItem]:
        if chapter.chapter_type == "qualification":
            return self._build_qualification_sections(checklist_rows, uploaded_materials)
        if chapter.chapter_type == "pricing":
            return self._build_pricing_sections(requirements_map, checklist_rows, uploaded_materials)
        return self._build_commercial_sections(requirements_map, uploaded_materials)

    def _build_qualification_sections(
        self,
        checklist_rows: list[tuple[MaterialRequirement, Requirement, Clause]],
        uploaded_materials: list[UserMaterial],
    ) -> list[DraftSectionItem]:
        sections: list[DraftSectionItem] = []
        order = 1
        for material_requirement, requirement, clause in checklist_rows:
            if material_requirement.material_type not in {
                "business_license",
                "qualification_certificate",
                "authorization_letter",
                "legal_representative_id",
                "tax_certificate",
                "social_security_certificate",
                "credit_report",
            }:
                continue
            matched_materials = self._match_materials(material_requirement, uploaded_materials)
            missing_info: list[str] = []
            if matched_materials:
                file_names = "、".join(material.file_name for material in matched_materials[:3])
                generated_text = (
                    f"本公司已按招标文件要求提交{material_requirement.material_name}，"
                    f"对应材料详见附件：{file_names}。"
                )
            else:
                generated_text = ""
                missing_info.append(f"未上传 {material_requirement.material_name}。")

            sections.append(
                DraftSectionItem(
                    section_title=material_requirement.material_name,
                    section_order=order,
                    generated_text=generated_text,
                    linked_requirement_codes=[requirement.id],
                    linked_material_ids=[material.id for material in matched_materials],
                    evidence_refs=[clause.source_evidence_id] if clause.source_evidence_id else [],
                    missing_info=missing_info,
                )
            )
            order += 1

        if not sections:
            sections.append(
                DraftSectionItem(
                    section_title="资格证明文件说明",
                    section_order=1,
                    generated_text="本章用于提交投标人资格与合规性证明文件。",
                    linked_requirement_codes=[],
                    linked_material_ids=[],
                    evidence_refs=[],
                    missing_info=["当前未生成资格类材料清单，请先执行 checklist 生成。"],
                )
            )
        return sections

    def _build_commercial_sections(
        self,
        requirements_map: dict[str, list[tuple[Requirement, Clause]]],
        uploaded_materials: list[UserMaterial],
    ) -> list[DraftSectionItem]:
        commercial_requirements = (
            requirements_map.get("commercial", [])
            + requirements_map.get("format", [])
            + requirements_map.get("deadline", [])
        )
        lines: list[str] = []
        evidence_refs: list[str] = []
        linked_requirement_codes: list[str] = []
        for requirement, clause in commercial_requirements[:12]:
            lines.append(f"1. 对“{clause.clause_title}”要求，本公司承诺按采购文件要求执行。")
            linked_requirement_codes.append(requirement.id)
            if clause.source_evidence_id:
                evidence_refs.append(clause.source_evidence_id)

        missing_info = [] if lines else ["未识别出可用于商务响应的条款。"]
        return [
            DraftSectionItem(
                section_title="商务响应承诺",
                section_order=1,
                generated_text="\n".join(lines) if lines else "",
                linked_requirement_codes=linked_requirement_codes,
                linked_material_ids=[],
                evidence_refs=evidence_refs,
                missing_info=missing_info,
            )
        ]

    def _build_pricing_sections(
        self,
        requirements_map: dict[str, list[tuple[Requirement, Clause]]],
        checklist_rows: list[tuple[MaterialRequirement, Requirement, Clause]],
        uploaded_materials: list[UserMaterial],
    ) -> list[DraftSectionItem]:
        pricing_rules = requirements_map.get("pricing", [])
        quote_materials = [row for row in checklist_rows if row[0].material_type == "quote_sheet"]
        matched_materials: list[UserMaterial] = []
        for material_requirement, _, _ in quote_materials:
            matched_materials.extend(self._match_materials(material_requirement, uploaded_materials))

        sections: list[DraftSectionItem] = []
        rule_lines = [f"1. {clause.clause_text}" for _, clause in pricing_rules[:8]]
        sections.append(
            DraftSectionItem(
                section_title="报价响应说明",
                section_order=1,
                generated_text="\n".join(rule_lines) if rule_lines else "",
                linked_requirement_codes=[requirement.id for requirement, _ in pricing_rules],
                linked_material_ids=[],
                evidence_refs=[clause.source_evidence_id for _, clause in pricing_rules if clause.source_evidence_id],
                missing_info=[] if rule_lines else ["未识别到明确的报价规则条款。"],
            )
        )

        if matched_materials:
            file_names = "、".join(material.file_name for material in matched_materials[:3])
            generated_text = f"本项目报价表已准备，相关文件包括：{file_names}。"
            missing_info: list[str] = []
        else:
            generated_text = ""
            missing_info = ["未上传报价表或未识别到报价材料。"]

        sections.append(
            DraftSectionItem(
                section_title="报价文件",
                section_order=2,
                generated_text=generated_text,
                linked_requirement_codes=[requirement.id for material_requirement, requirement, _ in quote_materials],
                linked_material_ids=[material.id for material in matched_materials],
                evidence_refs=[clause.source_evidence_id for _, _, clause in quote_materials if clause.source_evidence_id],
                missing_info=missing_info,
            )
        )
        return sections

    def _match_materials(self, material_requirement: MaterialRequirement, uploaded_materials: list[UserMaterial]) -> list[UserMaterial]:
        exact = [material for material in uploaded_materials if material.material_requirement_id == material_requirement.id]
        if exact:
            return exact
        return [material for material in uploaded_materials if material.material_type == material_requirement.material_type]

    def _enhance_sections_with_llm(
        self,
        chapter: Chapter,
        draft_sections: list[DraftSectionItem],
        requirements_map: dict[str, list[tuple[Requirement, Clause]]],
        checklist_rows: list[tuple[MaterialRequirement, Requirement, Clause]],
        uploaded_materials: list[UserMaterial],
    ) -> list[DraftSectionItem]:
        if not llm_draft_service.is_enabled():
            return draft_sections

        requirement_lookup = {
            requirement.id: (requirement, clause)
            for grouped in requirements_map.values()
            for requirement, clause in grouped
        }
        material_lookup = {material.id: material for material in uploaded_materials}

        enhanced: list[DraftSectionItem] = []
        for section in draft_sections:
            requirement_texts: list[str] = []
            evidence_quotes: list[str] = []
            material_names: list[str] = []

            for requirement_id in section.linked_requirement_codes:
                item = requirement_lookup.get(requirement_id)
                if not item:
                    continue
                requirement, clause = item
                requirement_texts.append(requirement.requirement_text)
                evidence_quotes.append(clause.clause_text)

            for material_id in section.linked_material_ids:
                material = material_lookup.get(material_id)
                if material:
                    material_names.append(material.file_name)

            rewritten = llm_draft_service.rewrite_section(
                LlmDraftContext(
                    chapter_title=chapter.title,
                    chapter_type=chapter.chapter_type,
                    section_title=section.section_title,
                    baseline_text=section.generated_text,
                    requirement_texts=requirement_texts,
                    evidence_quotes=evidence_quotes,
                    material_names=material_names,
                    missing_info=section.missing_info,
                )
            )
            if rewritten:
                section.generated_text = rewritten
            enhanced.append(section)
        return enhanced

    def _persist_sections(self, db: Session, chapter: Chapter, sections: list[DraftSectionItem]) -> None:
        db.execute(delete(DraftSection).where(DraftSection.chapter_id == chapter.id))
        for item in sections:
            db.add(
                DraftSection(
                    id=str(uuid4()),
                    chapter_id=chapter.id,
                    section_title=item.section_title,
                    section_order=item.section_order,
                    generated_text=item.generated_text,
                    source_summary_json=json.dumps(
                        {
                            "linked_requirement_codes": item.linked_requirement_codes,
                            "linked_material_ids": item.linked_material_ids,
                            "evidence_refs": item.evidence_refs,
                        },
                        ensure_ascii=False,
                    ),
                    missing_info_json=json.dumps(item.missing_info, ensure_ascii=False),
                    generation_status="pending" if item.missing_info else "generated",
                )
            )

    def _to_section_item(self, section: DraftSection) -> DraftSectionItem:
        source_summary = json.loads(section.source_summary_json) if section.source_summary_json else {}
        missing_info = json.loads(section.missing_info_json) if section.missing_info_json else []
        return DraftSectionItem(
            section_title=section.section_title,
            section_order=section.section_order,
            generated_text=section.generated_text,
            linked_requirement_codes=source_summary.get("linked_requirement_codes", []),
            linked_material_ids=source_summary.get("linked_material_ids", []),
            evidence_refs=source_summary.get("evidence_refs", []),
            missing_info=missing_info,
        )


draft_service = DraftService()
