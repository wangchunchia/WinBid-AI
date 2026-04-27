from collections import Counter
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.domain import Clause, MaterialRequirement, Requirement, TenderProject, UserMaterial
from app.schemas.checklist import (
    ChecklistGenerateRequest,
    ChecklistItem,
    ChecklistResponse,
    ChecklistResult,
    ChecklistSummary,
    MissingChecklistItem,
    MissingChecklistResponse,
)


class ChecklistService:
    def __init__(self) -> None:
        self._material_patterns = [
            ("business_license", "营业执照", ("营业执照", "统一社会信用代码")),
            ("authorization_letter", "授权委托书", ("授权委托书", "授权代表", "委托代理人")),
            ("legal_representative_id", "法定代表人身份证明", ("法定代表人", "身份证明")),
            ("bid_letter", "投标函", ("投标函", "响应函")),
            ("quote_sheet", "报价表", ("报价", "报价表", "单价", "总价", "限价")),
            ("performance_case", "类似项目业绩", ("业绩", "合同", "案例", "供货业绩")),
            ("qualification_certificate", "资质证书", ("资质", "证书", "许可")),
            ("technical_response", "技术响应表", ("技术参数", "技术响应", "规格", "偏离表")),
            ("commitment_letter", "承诺函", ("承诺", "保证", "售后")),
            ("tax_certificate", "纳税证明", ("纳税", "税收")),
            ("social_security_certificate", "社保证明", ("社保",)),
            ("credit_report", "信用证明材料", ("信用", "征信", "失信")),
        ]

    def generate_checklist(self, db: Session, project_id: str, payload: ChecklistGenerateRequest) -> ChecklistResponse:
        requirements = self._load_requirements(db, project_id, payload.requirement_codes)
        db.execute(delete(MaterialRequirement).where(MaterialRequirement.project_id == project_id))

        created_items: list[ChecklistItem] = []
        grouped_candidates: dict[str, dict[str, object]] = {}

        for requirement, clause in requirements:
            material_type, material_name = self._infer_material(requirement.requirement_text, clause.clause_category)
            submission_category = self._infer_submission_category(clause)
            if submission_category == "recommended" and not payload.include_recommended:
                continue

            existing = grouped_candidates.get(material_type)
            candidate = {
                "material_type": material_type,
                "material_name": material_name,
                "submission_category": submission_category,
                "requirement": requirement,
                "clause": clause,
            }
            if existing is None or self._category_priority(submission_category) > self._category_priority(str(existing["submission_category"])):
                grouped_candidates[material_type] = candidate

        for candidate in grouped_candidates.values():
            requirement = candidate["requirement"]
            clause = candidate["clause"]
            material_type = str(candidate["material_type"])
            material_name = str(candidate["material_name"])
            submission_category = str(candidate["submission_category"])

            material_requirement = MaterialRequirement(
                id=str(uuid4()),
                project_id=project_id,
                requirement_id=requirement.id,  # type: ignore[attr-defined]
                material_type=material_type,
                material_name=material_name,
                submission_category=submission_category,
                condition_expression=None,
                preferred_format=self._infer_preferred_format(material_type),
                checklist_guidance=self._build_guidance(material_name, material_type),
                alternative_allowed=material_type in {"credit_report", "performance_case"},
            )
            db.add(material_requirement)
            created_items.append(
                ChecklistItem(
                    material_code=material_requirement.id,
                    material_type=material_requirement.material_type,
                    material_name=material_requirement.material_name,
                    submission_category=material_requirement.submission_category,
                    condition_expression=material_requirement.condition_expression,
                    preferred_format=material_requirement.preferred_format,
                    checklist_guidance=material_requirement.checklist_guidance or "",
                    linked_requirement_codes=[requirement.id],  # type: ignore[attr-defined]
                    evidence_refs=[clause.source_evidence_id] if clause.source_evidence_id else [],  # type: ignore[attr-defined]
                )
            )

        db.commit()
        project = db.get(TenderProject, project_id)
        if project:
            project.status = "checklist_generated"
            db.commit()
        summary_counter = Counter(item.submission_category for item in created_items)

        return ChecklistResponse(
            run_id=str(uuid4()),
            agent_name="material_mapping_agent",
            project_id=project_id,
            status="success",
            warnings=[] if created_items else ["No checklist items generated from current requirements."],
            errors=[],
            result=ChecklistResult(
                checklist_items=created_items,
                grouped_summary=ChecklistSummary(
                    mandatory_count=summary_counter.get("mandatory", 0),
                    conditional_count=summary_counter.get("conditional", 0),
                    bonus_count=summary_counter.get("bonus", 0),
                    risk_count=summary_counter.get("risk", 0),
                ),
                missing_enterprise_capabilities=[],
            ),
        )

    def list_checklist(self, db: Session, project_id: str) -> ChecklistResult:
        rows = db.execute(
            select(MaterialRequirement, Requirement, Clause)
            .join(Requirement, MaterialRequirement.requirement_id == Requirement.id)
            .join(Clause, Requirement.clause_id == Clause.id)
            .where(MaterialRequirement.project_id == project_id)
            .order_by(MaterialRequirement.created_at.asc())
        ).all()

        items = [
            ChecklistItem(
                material_code=material_requirement.id,
                material_type=material_requirement.material_type,
                material_name=material_requirement.material_name,
                submission_category=material_requirement.submission_category,
                condition_expression=material_requirement.condition_expression,
                preferred_format=material_requirement.preferred_format,
                checklist_guidance=material_requirement.checklist_guidance or "",
                linked_requirement_codes=[requirement.id],
                evidence_refs=[clause.source_evidence_id] if clause.source_evidence_id else [],
            )
            for material_requirement, requirement, clause in rows
        ]
        summary_counter = Counter(item.submission_category for item in items)
        return ChecklistResult(
            checklist_items=items,
            grouped_summary=ChecklistSummary(
                mandatory_count=summary_counter.get("mandatory", 0),
                conditional_count=summary_counter.get("conditional", 0),
                bonus_count=summary_counter.get("bonus", 0),
                risk_count=summary_counter.get("risk", 0),
            ),
            missing_enterprise_capabilities=[],
        )

    def get_missing_checklist(self, db: Session, project_id: str) -> MissingChecklistResponse:
        rows = db.execute(
            select(MaterialRequirement, Requirement, Clause)
            .join(Requirement, MaterialRequirement.requirement_id == Requirement.id)
            .join(Clause, Requirement.clause_id == Clause.id)
            .where(MaterialRequirement.project_id == project_id)
            .order_by(MaterialRequirement.created_at.asc())
        ).all()
        uploaded_materials = db.scalars(
            select(UserMaterial).where(UserMaterial.project_id == project_id).order_by(UserMaterial.created_at.desc())
        ).all()

        missing_items: list[MissingChecklistItem] = []
        required_rows = [row for row in rows if row[0].submission_category in {"mandatory", "conditional", "risk"}]

        for material_requirement, requirement, clause in required_rows:
            if self._is_requirement_covered(material_requirement, uploaded_materials):
                continue
            missing_items.append(
                MissingChecklistItem(
                    material_code=material_requirement.id,
                    material_type=material_requirement.material_type,
                    material_name=material_requirement.material_name,
                    submission_category=material_requirement.submission_category,
                    reason=f"缺少 {material_requirement.material_name}，对应要求：{requirement.requirement_text}",
                    linked_requirement_codes=[requirement.id],
                    evidence_refs=[clause.source_evidence_id] if clause.source_evidence_id else [],
                )
            )

        return MissingChecklistResponse(
            project_id=project_id,
            total_required=len(required_rows),
            missing_count=len(missing_items),
            missing_items=missing_items,
        )

    def _load_requirements(self, db: Session, project_id: str, requirement_codes: list[str]) -> list[tuple[Requirement, Clause]]:
        stmt = (
            select(Requirement, Clause)
            .join(Clause, Requirement.clause_id == Clause.id)
            .where(Clause.project_id == project_id)
            .order_by(Requirement.created_at.asc())
        )
        if requirement_codes:
            stmt = stmt.where(Requirement.id.in_(requirement_codes))
        return list(db.execute(stmt).all())

    def _infer_material(self, text: str, clause_category: str) -> tuple[str, str]:
        for material_type, material_name, keywords in self._material_patterns:
            if any(keyword in text for keyword in keywords):
                return material_type, material_name
        if clause_category == "pricing":
            return "quote_sheet", "报价表"
        if clause_category == "qualification":
            return "qualification_certificate", "资格证明材料"
        if clause_category == "technical":
            return "technical_response", "技术响应材料"
        return "supporting_document", "响应支撑材料"

    def _infer_submission_category(self, clause: Clause) -> str:
        if clause.risk_level == "fatal":
            return "risk"
        if clause.importance_level == "mandatory":
            return "mandatory"
        if clause.importance_level == "conditional":
            return "conditional"
        if clause.importance_level == "bonus":
            return "bonus"
        return "recommended"

    def _infer_preferred_format(self, material_type: str) -> str:
        if material_type == "quote_sheet":
            return "xlsx"
        return "pdf"

    def _category_priority(self, submission_category: str) -> int:
        priority = {
            "recommended": 0,
            "bonus": 1,
            "conditional": 2,
            "mandatory": 3,
            "risk": 4,
        }
        return priority.get(submission_category, 0)

    def _build_guidance(self, material_name: str, material_type: str) -> str:
        if material_type == "quote_sheet":
            return "上传可编辑报价表或盖章扫描件，确保总价、单价和分项一致。"
        if material_type in {"business_license", "qualification_certificate", "tax_certificate", "social_security_certificate"}:
            return f"上传最新有效的{material_name}扫描件，确保内容清晰可识别。"
        return f"上传{material_name}相关文件，建议使用清晰 PDF 扫描件。"

    def _is_requirement_covered(self, material_requirement: MaterialRequirement, uploaded_materials: list[UserMaterial]) -> bool:
        for material in uploaded_materials:
            if material.material_requirement_id == material_requirement.id:
                return True
        for material in uploaded_materials:
            if material.material_type == material_requirement.material_type:
                return True
        return False


checklist_service = ChecklistService()
