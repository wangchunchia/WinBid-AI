import json
from collections import Counter
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.domain import Chapter, Clause, ComplianceIssue, DraftSection, MaterialRequirement, RejectionRisk, Requirement, TenderProject, UserMaterial
from app.schemas.compliance import (
    ComplianceCheckRequest,
    ComplianceCheckResponse,
    ComplianceIssueItem,
    ComplianceResult,
    CoverageReport,
    IssueSummary,
)


class ComplianceService:
    def run_check(self, db: Session, project_id: str, payload: ComplianceCheckRequest) -> ComplianceCheckResponse:
        issues = self._build_issues(db, project_id, payload)
        self._persist_issues(db, project_id, issues)
        coverage = self._build_coverage_report(db, project_id)
        summary = self._build_issue_summary(issues)
        overall_status = self._resolve_overall_status(summary)

        response = ComplianceCheckResponse(
            run_id=str(uuid4()),
            agent_name="compliance_check_agent",
            project_id=project_id,
            status="success",
            warnings=[] if payload.include_semantic_review else ["Semantic review disabled; only hard rules were checked."],
            errors=[],
            result=ComplianceResult(
                overall_status=overall_status,
                issue_summary=summary,
                issues=issues,
                coverage_report=coverage,
            ),
        )
        project = db.get(TenderProject, project_id)
        if project:
            project.status = "compliance_checked"
            db.commit()
        return response

    def list_issues(self, db: Session, project_id: str) -> list[ComplianceIssueItem]:
        issues = db.scalars(
            select(ComplianceIssue)
            .where(ComplianceIssue.project_id == project_id)
            .order_by(ComplianceIssue.created_at.asc())
        ).all()
        clause_code_by_id = {
            clause.id: clause.clause_code
            for clause in db.scalars(select(Clause).where(Clause.project_id == project_id)).all()
        }
        chapter_code_by_id = {
            chapter.id: chapter.chapter_code
            for chapter in db.scalars(select(Chapter).where(Chapter.project_id == project_id)).all()
        }
        return [
            ComplianceIssueItem(
                issue_code=issue.id,
                issue_type=issue.issue_type,
                severity=issue.severity,
                issue_title=issue.issue_title,
                issue_detail=issue.issue_detail,
                linked_clause_codes=[clause_code_by_id[issue.linked_clause_id]] if issue.linked_clause_id and issue.linked_clause_id in clause_code_by_id else [],
                linked_material_ids=[issue.linked_material_id] if issue.linked_material_id else [],
                linked_chapter_codes=[chapter_code_by_id[issue.linked_chapter_id]] if issue.linked_chapter_id and issue.linked_chapter_id in chapter_code_by_id else [],
                evidence_refs=[],
                resolution_suggestion=issue.resolution_suggestion or "",
            )
            for issue in issues
        ]

    def _build_issues(self, db: Session, project_id: str, payload: ComplianceCheckRequest) -> list[ComplianceIssueItem]:
        issues: list[ComplianceIssueItem] = []
        issues.extend(self._check_missing_materials(db, project_id))
        issues.extend(self._check_missing_chapters(db, project_id))
        issues.extend(self._check_pricing_readiness(db, project_id))
        issues.extend(self._check_rejection_risk_coverage(db, project_id))
        issues.extend(self._check_requirement_coverage(db, project_id))

        for idx, rule_result in enumerate(payload.rule_engine_results, start=1):
            if rule_result.status == "failed":
                issues.append(
                    ComplianceIssueItem(
                        issue_code=f"CI-RULE-{idx:03d}",
                        issue_type="rule_engine_failure",
                        severity=rule_result.severity,
                        issue_title="规则引擎校验失败",
                        issue_detail=rule_result.detail,
                        linked_clause_codes=[],
                        linked_material_ids=[],
                        linked_chapter_codes=[],
                        evidence_refs=[],
                        resolution_suggestion="根据规则结果补充材料或修复草稿后重新检查。",
                    )
                )
        return issues

    def _check_missing_materials(self, db: Session, project_id: str) -> list[ComplianceIssueItem]:
        checklist_rows = db.execute(
            select(MaterialRequirement, Requirement, Clause)
            .join(Requirement, MaterialRequirement.requirement_id == Requirement.id)
            .join(Clause, Requirement.clause_id == Clause.id)
            .where(MaterialRequirement.project_id == project_id)
            .order_by(MaterialRequirement.created_at.asc())
        ).all()
        uploaded_materials = db.scalars(
            select(UserMaterial).where(UserMaterial.project_id == project_id).order_by(UserMaterial.created_at.desc())
        ).all()
        issues: list[ComplianceIssueItem] = []
        for material_requirement, requirement, clause in checklist_rows:
            if material_requirement.submission_category not in {"mandatory", "conditional", "risk"}:
                continue
            if self._has_material(material_requirement, uploaded_materials):
                continue
            severity = "fatal" if material_requirement.submission_category == "risk" else "high"
            issues.append(
                ComplianceIssueItem(
                    issue_code=f"CI-MAT-{material_requirement.id[:8]}",
                    issue_type="missing_material",
                    severity=severity,
                    issue_title=f"缺少材料：{material_requirement.material_name}",
                    issue_detail=f"未找到 {material_requirement.material_name}，对应要求：{requirement.requirement_text}",
                    linked_clause_codes=[clause.clause_code],
                    linked_material_ids=[],
                    linked_chapter_codes=[],
                    evidence_refs=[clause.source_evidence_id] if clause.source_evidence_id else [],
                    resolution_suggestion=f"补充上传 {material_requirement.material_name} 后重新检查。",
                )
            )
        return issues

    def _check_missing_chapters(self, db: Session, project_id: str) -> list[ComplianceIssueItem]:
        chapters = db.scalars(
            select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_order.asc())
        ).all()
        issues: list[ComplianceIssueItem] = []
        for chapter in chapters:
            if chapter.chapter_type not in {"qualification", "commercial", "pricing"}:
                continue
            section_id = db.scalar(select(DraftSection.id).where(DraftSection.chapter_id == chapter.id).limit(1))
            if section_id is None:
                issues.append(
                    ComplianceIssueItem(
                        issue_code=f"CI-CH-{chapter.chapter_code}",
                        issue_type="missing_section",
                        severity="high",
                        issue_title=f"章节未生成：{chapter.title}",
                        issue_detail=f"章节 {chapter.title} 尚未生成草稿。",
                        linked_clause_codes=[],
                        linked_material_ids=[],
                        linked_chapter_codes=[chapter.chapter_code],
                        evidence_refs=[],
                        resolution_suggestion=f"执行章节生成，至少补全 {chapter.title}。",
                    )
                )
        return issues

    def _check_pricing_readiness(self, db: Session, project_id: str) -> list[ComplianceIssueItem]:
        pricing_chapter = db.scalar(
            select(Chapter).where(Chapter.project_id == project_id, Chapter.chapter_type == "pricing").limit(1)
        )
        quote_material = db.scalar(
            select(UserMaterial).where(UserMaterial.project_id == project_id, UserMaterial.material_type == "quote_sheet").limit(1)
        )
        if quote_material or not pricing_chapter:
            return []
        return [
            ComplianceIssueItem(
                issue_code="CI-PRICE-001",
                issue_type="pricing",
                severity="high",
                issue_title="报价材料缺失",
                issue_detail="项目存在报价章节，但未上传报价表或未识别到报价材料。",
                linked_clause_codes=[],
                linked_material_ids=[],
                linked_chapter_codes=[pricing_chapter.chapter_code],
                evidence_refs=[],
                resolution_suggestion="上传报价表或将报价材料关联到报价清单项后重新检查。",
            )
        ]

    def _check_rejection_risk_coverage(self, db: Session, project_id: str) -> list[ComplianceIssueItem]:
        risks = db.scalars(
            select(RejectionRisk).where(RejectionRisk.project_id == project_id).order_by(RejectionRisk.created_at.asc())
        ).all()
        chapter_rows = db.scalars(
            select(DraftSection)
            .join(Chapter, DraftSection.chapter_id == Chapter.id)
            .where(Chapter.project_id == project_id)
        ).all()
        covered_evidence_refs: set[str] = set()
        for section in chapter_rows:
            source_summary = json.loads(section.source_summary_json) if section.source_summary_json else {}
            covered_evidence_refs.update(source_summary.get("evidence_refs", []))

        issues: list[ComplianceIssueItem] = []
        for risk in risks:
            if risk.source_evidence_id and risk.source_evidence_id in covered_evidence_refs:
                continue
            clause = db.scalar(
                select(Clause).where(
                    Clause.project_id == project_id,
                    Clause.source_evidence_id == risk.source_evidence_id,
                ).limit(1)
            )
            issues.append(
                ComplianceIssueItem(
                    issue_code=f"CI-RISK-{risk.risk_code}",
                    issue_type="rejection",
                    severity="fatal" if risk.severity == "fatal" else "high",
                    issue_title="废标风险条款未覆盖",
                    issue_detail=f"风险条款未在任何生成章节中体现：{risk.risk_text}",
                    linked_clause_codes=[clause.clause_code] if clause else [],
                    linked_material_ids=[],
                    linked_chapter_codes=[],
                    evidence_refs=[risk.source_evidence_id] if risk.source_evidence_id else [],
                    resolution_suggestion="补充对应响应章节或增加明确承诺内容后重新检查。",
                )
            )
        return issues

    def _check_requirement_coverage(self, db: Session, project_id: str) -> list[ComplianceIssueItem]:
        requirements = db.scalars(
            select(Requirement)
            .join(Clause, Requirement.clause_id == Clause.id)
            .where(Clause.project_id == project_id, Requirement.mandatory_flag.is_(True))
            .order_by(Requirement.created_at.asc())
        ).all()
        section_rows = db.scalars(
            select(DraftSection)
            .join(Chapter, DraftSection.chapter_id == Chapter.id)
            .where(Chapter.project_id == project_id)
        ).all()
        covered_requirement_ids: set[str] = set()
        for section in section_rows:
            source_summary = json.loads(section.source_summary_json) if section.source_summary_json else {}
            covered_requirement_ids.update(source_summary.get("linked_requirement_codes", []))

        issues: list[ComplianceIssueItem] = []
        for requirement in requirements:
            if requirement.id in covered_requirement_ids:
                continue
            clause = db.get(Clause, requirement.clause_id)
            issues.append(
                ComplianceIssueItem(
                    issue_code=f"CI-REQ-{requirement.id[:8]}",
                    issue_type="unanswered_clause",
                    severity="medium",
                    issue_title="必需条款未覆盖",
                    issue_detail=f"要求项尚未在任何章节草稿中体现：{requirement.requirement_text}",
                    linked_clause_codes=[clause.clause_code] if clause else [],
                    linked_material_ids=[],
                    linked_chapter_codes=[],
                    evidence_refs=[requirement.source_evidence_id] if requirement.source_evidence_id else [],
                    resolution_suggestion="生成相关章节草稿，或将该要求补充到现有章节中。",
                )
            )
        return issues

    def _persist_issues(self, db: Session, project_id: str, issues: list[ComplianceIssueItem]) -> None:
        db.execute(delete(ComplianceIssue).where(ComplianceIssue.project_id == project_id))
        clause_id_by_code = {
            clause.clause_code: clause.id
            for clause in db.scalars(select(Clause).where(Clause.project_id == project_id)).all()
        }
        chapter_id_by_code = {
            chapter.chapter_code: chapter.id
            for chapter in db.scalars(select(Chapter).where(Chapter.project_id == project_id)).all()
        }
        for item in issues:
            db.add(
                ComplianceIssue(
                    id=item.issue_code,
                    project_id=project_id,
                    issue_type=item.issue_type,
                    severity=item.severity,
                    issue_title=item.issue_title,
                    issue_detail=item.issue_detail,
                    linked_clause_id=clause_id_by_code.get(item.linked_clause_codes[0]) if item.linked_clause_codes else None,
                    linked_material_id=item.linked_material_ids[0] if item.linked_material_ids else None,
                    linked_chapter_id=chapter_id_by_code.get(item.linked_chapter_codes[0]) if item.linked_chapter_codes else None,
                    resolution_suggestion=item.resolution_suggestion,
                    status="open",
                )
            )
        db.commit()

    def _build_coverage_report(self, db: Session, project_id: str) -> CoverageReport:
        requirement_ids = db.scalars(
            select(Requirement.id)
            .join(Clause, Requirement.clause_id == Clause.id)
            .where(Clause.project_id == project_id)
        ).all()
        total_count = len(requirement_ids)
        section_rows = db.scalars(
            select(DraftSection)
            .join(Chapter, DraftSection.chapter_id == Chapter.id)
            .where(Chapter.project_id == project_id)
        ).all()
        covered_requirement_ids: set[str] = set()
        for section in section_rows:
            source_summary = json.loads(section.source_summary_json) if section.source_summary_json else {}
            covered_requirement_ids.update(source_summary.get("linked_requirement_codes", []))
        covered_count = len(covered_requirement_ids)
        return CoverageReport(
            total_requirements=total_count,
            covered_requirements=min(covered_count, total_count),
            uncovered_requirements=max(total_count - covered_count, 0),
        )

    def _build_issue_summary(self, issues: list[ComplianceIssueItem]) -> IssueSummary:
        counter = Counter(issue.severity for issue in issues)
        return IssueSummary(
            fatal=counter.get("fatal", 0),
            high=counter.get("high", 0),
            medium=counter.get("medium", 0),
            low=counter.get("low", 0),
        )

    def _resolve_overall_status(self, summary: IssueSummary) -> str:
        if summary.fatal:
            return "fatal_risk"
        if summary.high:
            return "high_risk"
        if summary.medium:
            return "medium_risk"
        return "pass"

    def _has_material(self, material_requirement: MaterialRequirement, uploaded_materials: list[UserMaterial]) -> bool:
        for material in uploaded_materials:
            if material.material_requirement_id == material_requirement.id:
                return True
        for material in uploaded_materials:
            if material.material_type == material_requirement.material_type:
                return True
        return False


compliance_service = ComplianceService()
