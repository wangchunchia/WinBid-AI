import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.domain import Chapter, Clause, ComplianceIssue, MaterialRequirement, Requirement, SourceDocument, UserMaterial
from app.schemas.bid_agent import AgentActionPayload, BidProjectAgentDecision, ProjectStatusSnapshot


class BidProjectAgentService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def get_next_action(self, db: Session, project_id: str) -> BidProjectAgentDecision:
        snapshot = self.build_snapshot(db, project_id)

        if self._settings.openai_enable_agent_decision and self._settings.openai_api_key:
            llm_decision = self._try_llm_decision(snapshot)
            if llm_decision:
                return llm_decision

        return self._heuristic_decision(snapshot)

    def build_snapshot(self, db: Session, project_id: str) -> ProjectStatusSnapshot:
        from app.models.domain import TenderProject

        project = db.get(TenderProject, project_id)
        project_status = project.status if project else "unknown"
        tender_document_count = db.scalar(
            select(func.count()).select_from(SourceDocument).where(SourceDocument.project_id == project_id)
        ) or 0
        parsed_document_count = db.scalar(
            select(func.count())
            .select_from(SourceDocument)
            .where(SourceDocument.project_id == project_id, SourceDocument.parse_status == "parsed")
        ) or 0
        clause_count = db.scalar(select(func.count()).select_from(Clause).where(Clause.project_id == project_id)) or 0
        requirement_count = (
            db.scalar(
                select(func.count())
                .select_from(Requirement)
                .join(Clause, Requirement.clause_id == Clause.id)
                .where(Clause.project_id == project_id)
            )
            or 0
        )
        checklist_item_count = db.scalar(
            select(func.count()).select_from(MaterialRequirement).where(MaterialRequirement.project_id == project_id)
        ) or 0
        uploaded_material_count = db.scalar(
            select(func.count()).select_from(UserMaterial).where(UserMaterial.project_id == project_id)
        ) or 0
        draft_chapter_count = db.scalar(
            select(func.count()).select_from(Chapter).where(Chapter.project_id == project_id)
        ) or 0
        generated_draft_chapter_count = db.scalar(
            select(func.count())
            .select_from(Chapter)
            .where(Chapter.project_id == project_id, Chapter.generation_status == "generated")
        ) or 0
        compliance_issue_count = db.scalar(
            select(func.count()).select_from(ComplianceIssue).where(ComplianceIssue.project_id == project_id)
        ) or 0
        fatal_issue_count = db.scalar(
            select(func.count())
            .select_from(ComplianceIssue)
            .where(ComplianceIssue.project_id == project_id, ComplianceIssue.severity == "fatal")
        ) or 0
        high_issue_count = db.scalar(
            select(func.count())
            .select_from(ComplianceIssue)
            .where(ComplianceIssue.project_id == project_id, ComplianceIssue.severity == "high")
        ) or 0

        missing_material_types = self._list_missing_material_types(db, project_id)
        available_chapter_codes = db.scalars(
            select(Chapter.chapter_code).where(Chapter.project_id == project_id).order_by(Chapter.chapter_order.asc())
        ).all()
        generated_chapter_codes = db.scalars(
            select(Chapter.chapter_code)
            .where(Chapter.project_id == project_id, Chapter.generation_status == "generated")
            .order_by(Chapter.chapter_order.asc())
        ).all()
        fatal_issue_codes = db.scalars(
            select(ComplianceIssue.id)
            .where(ComplianceIssue.project_id == project_id, ComplianceIssue.severity == "fatal")
            .order_by(ComplianceIssue.created_at.asc())
        ).all()
        high_issue_codes = db.scalars(
            select(ComplianceIssue.id)
            .where(ComplianceIssue.project_id == project_id, ComplianceIssue.severity == "high")
            .order_by(ComplianceIssue.created_at.asc())
        ).all()

        return ProjectStatusSnapshot(
            project_id=project_id,
            project_status=project_status,
            tender_document_count=tender_document_count,
            parsed_document_count=parsed_document_count,
            clause_count=clause_count,
            requirement_count=requirement_count,
            checklist_item_count=checklist_item_count,
            missing_material_count=len(missing_material_types),
            uploaded_material_count=uploaded_material_count,
            draft_chapter_count=draft_chapter_count,
            generated_draft_chapter_count=generated_draft_chapter_count,
            compliance_issue_count=compliance_issue_count,
            fatal_issue_count=fatal_issue_count,
            high_issue_count=high_issue_count,
            available_chapter_codes=available_chapter_codes,
            generated_chapter_codes=generated_chapter_codes,
            missing_material_types=missing_material_types,
            fatal_issue_codes=fatal_issue_codes,
            high_issue_codes=high_issue_codes,
        )

    def _list_missing_material_types(self, db: Session, project_id: str) -> list[str]:
        checklist_rows = db.scalars(
            select(MaterialRequirement).where(
                MaterialRequirement.project_id == project_id,
                MaterialRequirement.submission_category.in_(["mandatory", "conditional", "risk"]),
            )
        ).all()
        uploaded_materials = db.scalars(
            select(UserMaterial).where(UserMaterial.project_id == project_id)
        ).all()
        missing_types: list[str] = []
        for requirement in checklist_rows:
            exact = any(material.material_requirement_id == requirement.id for material in uploaded_materials)
            same_type = any(material.material_type == requirement.material_type for material in uploaded_materials)
            if not exact and not same_type:
                missing_types.append(requirement.material_type)
        return missing_types

    def _heuristic_decision(self, snapshot: ProjectStatusSnapshot) -> BidProjectAgentDecision:
        if snapshot.tender_document_count == 0:
            return BidProjectAgentDecision(
                project_id=snapshot.project_id,
                agent_mode="heuristic",
                current_assessment="项目尚未登记任何招标文件，无法启动后续工作流。",
                next_action="upload_tender_documents",
                reason="招标文件是解析、清单生成和标书生成的前置输入。",
                requires_user_input=True,
                confidence=0.99,
                action_payload=AgentActionPayload(
                    endpoint=f"/api/v1/projects/{snapshot.project_id}/tender-documents",
                    method="POST",
                    notes=["至少上传招标正文；如有附件和澄清文件也应一并登记。"],
                ),
                state_snapshot=snapshot,
            )
        if snapshot.parsed_document_count == 0 or snapshot.clause_count == 0:
            return BidProjectAgentDecision(
                project_id=snapshot.project_id,
                agent_mode="heuristic",
                current_assessment="已登记招标文件，但尚未完成有效解析。",
                next_action="parse_tender_package",
                reason="需要先解析招标文件，才能提取条款、要求项和目录建议。",
                requires_user_input=False,
                confidence=0.97,
                action_payload=AgentActionPayload(
                    endpoint=f"/api/v1/projects/{snapshot.project_id}/parse",
                    method="POST",
                    notes=["建议先解析全部招标正文、附件和澄清文件。"],
                ),
                state_snapshot=snapshot,
            )
        if snapshot.checklist_item_count == 0:
            return BidProjectAgentDecision(
                project_id=snapshot.project_id,
                agent_mode="heuristic",
                current_assessment="招标条款已解析，但尚未生成投标材料清单。",
                next_action="generate_checklist",
                reason="材料清单是材料收集、草稿生成和合规检查的前置步骤。",
                requires_user_input=False,
                confidence=0.95,
                action_payload=AgentActionPayload(
                    endpoint=f"/api/v1/projects/{snapshot.project_id}/checklist/generate",
                    method="POST",
                ),
                state_snapshot=snapshot,
            )
        if snapshot.missing_material_count > 0:
            return BidProjectAgentDecision(
                project_id=snapshot.project_id,
                agent_mode="heuristic",
                current_assessment=f"材料清单已生成，但仍缺少 {snapshot.missing_material_count} 项必需或高风险材料。",
                next_action="upload_missing_materials",
                reason="在关键材料缺失时继续生成标书会导致章节缺口和合规风险。",
                requires_user_input=True,
                confidence=0.94,
                action_payload=AgentActionPayload(
                    endpoint=f"/api/v1/projects/{snapshot.project_id}/checklist/missing",
                    method="GET",
                    notes=["优先补齐 mandatory 和 risk 类材料。"],
                ),
                state_snapshot=snapshot,
            )
        if snapshot.generated_draft_chapter_count == 0:
            return BidProjectAgentDecision(
                project_id=snapshot.project_id,
                agent_mode="heuristic",
                current_assessment="关键材料基本齐全，但尚未生成任何章节草稿。",
                next_action="generate_chapter_draft",
                reason="需要先生成资格、商务和报价章节草稿，才能做后续合规检查。",
                requires_user_input=False,
                confidence=0.92,
                action_payload=AgentActionPayload(
                    endpoint=f"/api/v1/projects/{snapshot.project_id}/drafts/generate",
                    method="POST",
                    chapter_codes=["C01", "C02", "C04"],
                ),
                state_snapshot=snapshot,
            )
        if snapshot.compliance_issue_count == 0:
            return BidProjectAgentDecision(
                project_id=snapshot.project_id,
                agent_mode="heuristic",
                current_assessment="章节草稿已生成，但尚未进行正式合规检查。",
                next_action="run_compliance_check",
                reason="必须先进行基础合规检查，才能判断是否适合进入导出或人工复核阶段。",
                requires_user_input=False,
                confidence=0.91,
                action_payload=AgentActionPayload(
                    endpoint=f"/api/v1/projects/{snapshot.project_id}/compliance/check",
                    method="POST",
                ),
                state_snapshot=snapshot,
            )
        if snapshot.fatal_issue_count > 0 or snapshot.high_issue_count > 0:
            return BidProjectAgentDecision(
                project_id=snapshot.project_id,
                agent_mode="heuristic",
                current_assessment=f"当前存在 {snapshot.fatal_issue_count} 个 fatal 和 {snapshot.high_issue_count} 个 high 风险问题。",
                next_action="resolve_compliance_issues",
                reason="在 fatal/high 问题未解决前，不应进入导出或最终提交阶段。",
                requires_user_input=True,
                confidence=0.96,
                action_payload=AgentActionPayload(
                    endpoint=f"/api/v1/projects/{snapshot.project_id}/compliance/issues",
                    method="GET",
                    notes=["优先处理 fatal，其次处理 high 风险问题。"],
                ),
                state_snapshot=snapshot,
            )

        return BidProjectAgentDecision(
            project_id=snapshot.project_id,
            agent_mode="heuristic",
            current_assessment="项目已完成解析、清单、草稿和基础合规检查，当前没有 fatal/high 风险阻塞项。",
            next_action="ready_for_export",
            reason="当前已具备进入人工复核和导出阶段的条件。",
            requires_user_input=False,
            confidence=0.9,
            action_payload=AgentActionPayload(
                endpoint=f"/api/v1/projects/{snapshot.project_id}/export",
                method="POST",
                notes=["建议先人工复核章节文本、材料附件和风险报告。"],
            ),
            state_snapshot=snapshot,
        )

    def _try_llm_decision(self, snapshot: ProjectStatusSnapshot) -> BidProjectAgentDecision | None:
        try:
            from openai import OpenAI
        except ImportError:
            return None

        client_kwargs: dict[str, object] = {
            "api_key": self._settings.openai_api_key,
            "timeout": self._settings.openai_timeout_seconds,
        }
        if self._settings.openai_base_url:
            client_kwargs["base_url"] = self._settings.openai_base_url
        client = OpenAI(**client_kwargs)

        prompt = self._build_llm_prompt(snapshot)
        try:
            response = client.responses.create(
                model=self._settings.openai_model,
                instructions=(
                    "你是自动写标书系统的项目总控 Agent。"
                    "你必须基于项目状态判断下一步最合理的单一动作。"
                    "动作只能从给定动作集合中选择。"
                    "必须输出合法 JSON，不要输出解释性前后缀。"
                ),
                input=prompt,
                max_output_tokens=700,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "bid_project_agent_decision",
                        "schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "current_assessment": {"type": "string"},
                                "next_action": {
                                    "type": "string",
                                    "enum": [
                                        "upload_tender_documents",
                                        "parse_tender_package",
                                        "generate_checklist",
                                        "upload_missing_materials",
                                        "generate_chapter_draft",
                                        "run_compliance_check",
                                        "resolve_compliance_issues",
                                        "ready_for_export",
                                    ],
                                },
                                "reason": {"type": "string"},
                                "requires_user_input": {"type": "boolean"},
                                "confidence": {"type": "number"},
                                "action_payload": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "endpoint": {"type": ["string", "null"]},
                                        "method": {"type": ["string", "null"]},
                                        "chapter_codes": {"type": "array", "items": {"type": "string"}},
                                        "missing_material_types": {"type": "array", "items": {"type": "string"}},
                                        "blocking_issue_codes": {"type": "array", "items": {"type": "string"}},
                                        "notes": {"type": "array", "items": {"type": "string"}},
                                    },
                                    "required": ["endpoint", "method", "chapter_codes", "missing_material_types", "blocking_issue_codes", "notes"],
                                },
                            },
                            "required": ["current_assessment", "next_action", "reason", "requires_user_input", "confidence", "action_payload"],
                        },
                    }
                },
            )
        except Exception:
            return None

        text = getattr(response, "output_text", None)
        if not text:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None

        return BidProjectAgentDecision(
            project_id=snapshot.project_id,
            agent_mode="llm",
            current_assessment=data["current_assessment"],
            next_action=data["next_action"],
            reason=data["reason"],
            requires_user_input=bool(data["requires_user_input"]),
            confidence=float(data["confidence"]),
            action_payload=AgentActionPayload(**data["action_payload"]),
            state_snapshot=snapshot,
        )

    def _build_llm_prompt(self, snapshot: ProjectStatusSnapshot) -> str:
        return (
            "你需要为自动写标书项目判断下一步动作。\n"
            "动作集合：\n"
            "- upload_tender_documents\n"
            "- parse_tender_package\n"
            "- generate_checklist\n"
            "- upload_missing_materials\n"
            "- generate_chapter_draft\n"
            "- run_compliance_check\n"
            "- resolve_compliance_issues\n"
            "- ready_for_export\n\n"
            "决策原则：\n"
            "1. 只选择一个最重要的下一步动作。\n"
            "2. 优先处理阻塞项。\n"
            "3. fatal/high 风险优先于导出。\n"
            "4. 缺材料时不要贸然生成完整草稿。\n"
            "5. 如果尚未解析、尚未生成清单、尚未生成草稿或尚未检查合规，应优先补齐流程。\n\n"
            f"项目状态快照：\n{snapshot.model_dump_json(indent=2)}\n"
        )


bid_project_agent_service = BidProjectAgentService()
