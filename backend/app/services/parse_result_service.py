import json
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.domain import Chapter, Clause, ComplianceIssue, DraftSection, Evidence, ParseOpenQuestion, PricingRule, RejectionRisk, Requirement, TenderProject
from app.schemas.parse import (
    ClauseItem,
    DirectorySuggestionItem,
    EvidenceItem,
    OpenQuestionItem,
    PricingRuleItem,
    RejectionRiskItem,
    RequirementItem,
    StructureTemplateRequest,
    StructureTemplateResponse,
    StructureTemplateResult,
)


class ParseResultService:
    def generate_structure_template(
        self,
        db: Session,
        project_id: str,
        payload: StructureTemplateRequest,
        regenerated: bool,
    ) -> StructureTemplateResponse:
        clauses = db.scalars(select(Clause).where(Clause.project_id == project_id).order_by(Clause.created_at.asc())).all()
        pricing_rules = db.scalars(
            select(PricingRule).where(PricingRule.project_id == project_id).order_by(PricingRule.created_at.asc())
        ).all()
        if not clauses and not pricing_rules:
            raise ValueError("No parsed clauses available. Please parse tender documents first.")

        template_mode = self._resolve_template_mode(payload)
        chapters, rationale = self._build_structure_template(clauses, pricing_rules, payload, template_mode)

        if payload.replace_existing:
            self._replace_structure_template(db, project_id, chapters)
            project = db.get(TenderProject, project_id)
            if project:
                project.status = "template_generated"
            db.commit()

        return StructureTemplateResponse(
            run_id=str(uuid4()),
            agent_name="structure_template_agent",
            project_id=project_id,
            status="success",
            warnings=[],
            errors=[],
            result=StructureTemplateResult(
                template_mode=template_mode,
                regenerated=regenerated,
                rationale=rationale,
                chapters=chapters,
            ),
        )

    def get_evidence(self, db: Session, project_id: str, evidence_id: str) -> EvidenceItem | None:
        evidence = db.scalar(
            select(Evidence).where(Evidence.project_id == project_id, Evidence.id == evidence_id)
        )
        if not evidence:
            return None
        confidence = float(evidence.confidence_score) if evidence.confidence_score is not None else None
        return EvidenceItem(
            evidence_id=evidence.id,
            document_id=evidence.document_id,
            chunk_id=evidence.chunk_id,
            page_no=evidence.page_no,
            quote_text=evidence.quote_text,
            normalized_text=evidence.normalized_text,
            evidence_type=evidence.evidence_type,
            confidence_score=confidence,
        )

    def list_directory_suggestions(self, db: Session, project_id: str) -> list[DirectorySuggestionItem]:
        chapters = db.scalars(
            select(Chapter)
            .where(Chapter.project_id == project_id)
            .order_by(Chapter.chapter_order.asc(), Chapter.created_at.asc())
        ).all()
        return [
            DirectorySuggestionItem(
                chapter_code=chapter.chapter_code,
                title=chapter.title,
                chapter_type=chapter.chapter_type,
                mandatory_flag=True,
                evidence_refs=[],
            )
            for chapter in chapters
        ]

    def list_clauses(self, db: Session, project_id: str) -> list[ClauseItem]:
        clauses = db.scalars(
            select(Clause)
            .where(Clause.project_id == project_id)
            .order_by(Clause.created_at.asc(), Clause.clause_code.asc())
        ).all()
        return [
            ClauseItem(
                clause_code=clause.clause_code,
                clause_category=clause.clause_category,
                clause_title=clause.clause_title,
                clause_text=clause.clause_text,
                importance_level=clause.importance_level,
                risk_level=clause.risk_level,
                needs_response=clause.needs_response,
                evidence_refs=[clause.source_evidence_id] if clause.source_evidence_id else [],
            )
            for clause in clauses
        ]

    def list_requirements(self, db: Session, project_id: str) -> list[RequirementItem]:
        rows = db.execute(
            select(Requirement, Clause.clause_code)
            .join(Clause, Requirement.clause_id == Clause.id)
            .where(Clause.project_id == project_id)
            .order_by(Requirement.created_at.asc())
        ).all()
        return [
            RequirementItem(
                requirement_code=requirement.id,
                linked_clause_code=clause_code,
                requirement_type=requirement.requirement_type,
                requirement_text=requirement.requirement_text,
                response_mode=requirement.response_mode,
                acceptance_rule=requirement.acceptance_rule,
                mandatory_flag=requirement.mandatory_flag,
                evidence_refs=[requirement.source_evidence_id] if requirement.source_evidence_id else [],
            )
            for requirement, clause_code in rows
        ]

    def list_pricing_rules(self, db: Session, project_id: str) -> list[PricingRuleItem]:
        pricing_rules = db.scalars(
            select(PricingRule)
            .where(PricingRule.project_id == project_id)
            .order_by(PricingRule.created_at.asc(), PricingRule.rule_code.asc())
        ).all()
        return [
            PricingRuleItem(
                rule_code=rule.rule_code,
                rule_text=rule.rule_text,
                evidence_refs=[rule.source_evidence_id] if rule.source_evidence_id else [],
            )
            for rule in pricing_rules
        ]

    def list_rejection_risks(self, db: Session, project_id: str) -> list[RejectionRiskItem]:
        risks = db.scalars(
            select(RejectionRisk)
            .where(RejectionRisk.project_id == project_id)
            .order_by(RejectionRisk.created_at.asc(), RejectionRisk.risk_code.asc())
        ).all()
        return [
            RejectionRiskItem(
                risk_code=risk.risk_code,
                severity=risk.severity,
                risk_text=risk.risk_text,
                evidence_refs=[risk.source_evidence_id] if risk.source_evidence_id else [],
            )
            for risk in risks
        ]

    def list_open_questions(self, db: Session, project_id: str) -> list[OpenQuestionItem]:
        questions = db.scalars(
            select(ParseOpenQuestion)
            .where(ParseOpenQuestion.project_id == project_id)
            .order_by(ParseOpenQuestion.created_at.asc())
        ).all()
        return [
            OpenQuestionItem(
                question=item.question,
                related_document_ids=json.loads(item.related_document_ids_json) if item.related_document_ids_json else [],
            )
            for item in questions
        ]

    def _resolve_template_mode(self, payload: StructureTemplateRequest) -> str:
        explicit = payload.template_mode.strip().lower()
        if explicit in {"basic", "compact", "detailed"}:
            mode = explicit
        else:
            mode = "basic"

        instruction = (payload.custom_instruction or "").strip()
        if "精简" in instruction or "简洁" in instruction:
            return "compact"
        if "详细" in instruction or "完整" in instruction:
            return "detailed"
        return mode

    def _build_structure_template(
        self,
        clauses: list[Clause],
        pricing_rules: list[PricingRule],
        payload: StructureTemplateRequest,
        template_mode: str,
    ) -> tuple[list[DirectorySuggestionItem], list[str]]:
        categories = {clause.clause_category for clause in clauses}
        has_technical = "technical" in categories
        has_pricing = bool(pricing_rules) or "pricing" in categories
        has_rejection = "rejection" in categories or any(clause.risk_level == "fatal" for clause in clauses)

        if payload.include_technical_chapter is not None:
            has_technical = payload.include_technical_chapter

        chapters: list[DirectorySuggestionItem] = [
            DirectorySuggestionItem(
                chapter_code="C01",
                title="资格证明文件",
                chapter_type="qualification",
                mandatory_flag=True,
                evidence_refs=[],
            ),
            DirectorySuggestionItem(
                chapter_code="C02",
                title="商务响应文件",
                chapter_type="commercial",
                mandatory_flag=True,
                evidence_refs=[],
            ),
        ]
        rationale = ["默认保留资格和商务两类基础章节。"]

        if has_technical:
            chapters.append(
                DirectorySuggestionItem(
                    chapter_code="C03",
                    title="技术响应文件",
                    chapter_type="technical",
                    mandatory_flag=True,
                    evidence_refs=[],
                )
            )
            rationale.append("识别到技术参数或技术响应条款，加入技术响应章节。")

        if has_pricing:
            chapters.append(
                DirectorySuggestionItem(
                    chapter_code="C04",
                    title="报价文件",
                    chapter_type="pricing",
                    mandatory_flag=True,
                    evidence_refs=[],
                )
            )
            rationale.append("识别到报价规则或报价条款，加入报价章节。")

        if template_mode == "detailed" or has_rejection:
            chapters.append(
                DirectorySuggestionItem(
                    chapter_code="C05",
                    title="重点条款响应表",
                    chapter_type="response_matrix",
                    mandatory_flag=has_rejection,
                    evidence_refs=[],
                )
            )
            rationale.append("为便于逐条响应关键风险条款，加入重点条款响应表章节。")

        if payload.include_appendix_chapter or template_mode == "detailed":
            chapters.append(
                DirectorySuggestionItem(
                    chapter_code="C99",
                    title="附件与补充材料",
                    chapter_type="appendix",
                    mandatory_flag=False,
                    evidence_refs=[],
                )
            )
            rationale.append("按用户偏好保留附件与补充材料章节。")

        if template_mode == "compact":
            rationale.append("当前使用精简模板模式，不额外增加补充章节。")
        elif template_mode == "basic":
            rationale.append("当前使用基础模板模式，保留最常见投标章节结构。")
        else:
            rationale.append("当前使用详细模板模式，增加逐条响应与附件章节。")

        return chapters, rationale

    def _replace_structure_template(
        self,
        db: Session,
        project_id: str,
        chapters: list[DirectorySuggestionItem],
    ) -> None:
        existing_chapters = db.scalars(
            select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_order.asc())
        ).all()
        existing_chapter_ids = [chapter.id for chapter in existing_chapters]
        if existing_chapter_ids:
            db.execute(delete(DraftSection).where(DraftSection.chapter_id.in_(existing_chapter_ids)))
            db.execute(delete(ComplianceIssue).where(ComplianceIssue.project_id == project_id))
        db.execute(delete(Chapter).where(Chapter.project_id == project_id))

        for index, chapter in enumerate(chapters, start=1):
            db.add(
                Chapter(
                    id=str(uuid4()),
                    project_id=project_id,
                    chapter_code=chapter.chapter_code,
                    title=chapter.title,
                    chapter_order=index,
                    chapter_type=chapter.chapter_type,
                    generation_status="suggested",
                )
            )


parse_result_service = ParseResultService()
