import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import PlanStep, ProjectPlan, TenderProject
from app.schemas.bid_agent import (
    AgentPlanRequest,
    AgentPlanResponse,
    PlanStepPayload,
    PlanStepView,
    ProjectPlanView,
    ProjectStatusSnapshot,
    SolveExecutionItem,
    SolveRequest,
    SolveResponse,
    SolveStepRequest,
    SolveStepResponse,
)
from app.schemas.checklist import ChecklistGenerateRequest
from app.schemas.compliance import ComplianceCheckRequest
from app.schemas.draft import DraftGenerateRequest
from app.schemas.parse import ParseRequest
from app.services.bid_project_agent_service import bid_project_agent_service
from app.services.checklist_service import checklist_service
from app.services.compliance_service import compliance_service
from app.services.draft_service import draft_service
from app.services.orchestrator_service import orchestrator_service
from app.services.project_memory_service import ProjectMemoryPolicy, project_memory_service


class PlanAndSolveService:
    def create_plan(self, db: Session, project_id: str, payload: AgentPlanRequest) -> AgentPlanResponse:
        existing = self.get_latest_plan(db, project_id)
        if existing and not payload.refresh_existing:
            snapshot = bid_project_agent_service.build_snapshot(db, project_id)
            memory_policy = project_memory_service.resolve_policy(db, project_id)
            self._reconcile_steps(db, existing, snapshot, memory_policy)
            self._refresh_plan_state(db, existing, snapshot, memory_policy)
            db.commit()
            return AgentPlanResponse(
                project_id=project_id,
                planner_mode="heuristic",
                plan=self._to_plan_view(db, existing, snapshot),
            )

        if existing and payload.refresh_existing and existing.plan_status not in {"completed", "superseded"}:
            existing.plan_status = "superseded"

        snapshot = bid_project_agent_service.build_snapshot(db, project_id)
        memory_policy = project_memory_service.resolve_policy(db, project_id)
        plan = ProjectPlan(
            id=str(uuid4()),
            project_id=project_id,
            goal=payload.goal,
            plan_status="in_progress",
            current_step_code=None,
            overall_assessment=self._build_assessment(snapshot, memory_policy),
            blocking_reason=None,
            requires_user_input=False,
        )
        db.add(plan)
        db.flush()

        for step_view in self._build_plan_steps(snapshot, memory_policy):
            db.add(
                PlanStep(
                    id=str(uuid4()),
                    plan_id=plan.id,
                    step_code=step_view.step_code,
                    step_title=step_view.step_title,
                    action_name=step_view.action_name,
                    step_order=step_view.step_order,
                    status=step_view.status,
                    depends_on_json=json.dumps(step_view.depends_on_step_codes, ensure_ascii=False),
                    action_payload_json=step_view.action_payload.model_dump_json(),
                    result_summary=step_view.result_summary,
                    result_payload_json=json.dumps(step_view.result_payload, ensure_ascii=False),
                    requires_user_input=step_view.requires_user_input,
                    blocking_reason=step_view.blocking_reason,
                )
            )

        db.flush()
        self._refresh_plan_state(db, plan, snapshot, memory_policy)
        db.commit()
        return AgentPlanResponse(
            project_id=project_id,
            planner_mode="heuristic",
            plan=self._to_plan_view(db, plan, snapshot),
        )

    def get_latest_plan(self, db: Session, project_id: str) -> ProjectPlan | None:
        return db.scalar(
            select(ProjectPlan)
            .where(ProjectPlan.project_id == project_id, ProjectPlan.plan_status != "superseded")
            .order_by(ProjectPlan.created_at.desc())
            .limit(1)
        )

    def get_plan_view(self, db: Session, project_id: str) -> ProjectPlanView | None:
        plan = self.get_latest_plan(db, project_id)
        if plan is None:
            return None
        snapshot = bid_project_agent_service.build_snapshot(db, project_id)
        memory_policy = project_memory_service.resolve_policy(db, project_id)
        self._reconcile_steps(db, plan, snapshot, memory_policy)
        self._refresh_plan_state(db, plan, snapshot, memory_policy)
        db.commit()
        return self._to_plan_view(db, plan, snapshot)

    def solve_step(self, db: Session, project_id: str, payload: SolveStepRequest) -> SolveStepResponse:
        plan = self._resolve_plan(db, project_id, payload.plan_id)
        if plan is None:
            created = self.create_plan(db, project_id, AgentPlanRequest())
            plan = self._resolve_plan(db, project_id, created.plan.plan_id)
            if plan is None:
                raise ValueError("Unable to initialize plan")

        snapshot_before = bid_project_agent_service.build_snapshot(db, project_id)
        memory_policy = project_memory_service.resolve_policy(db, project_id)
        self._reconcile_steps(db, plan, snapshot_before, memory_policy)
        step = self._select_step(db, plan, payload.step_code)
        if step is None:
            self._refresh_plan_state(db, plan, snapshot_before, memory_policy)
            db.commit()
            return SolveStepResponse(
                project_id=project_id,
                plan_id=plan.id,
                executed=False,
                executed_step_code=None,
                execution_status="completed",
                message="当前计划已无可执行步骤。",
                plan=self._to_plan_view(db, plan, snapshot_before),
            )

        if step.requires_user_input:
            step.status = "blocked"
            self._refresh_plan_state(db, plan, snapshot_before, memory_policy)
            db.commit()
            return SolveStepResponse(
                project_id=project_id,
                plan_id=plan.id,
                executed=False,
                executed_step_code=step.step_code,
                execution_status="blocked",
                message=step.blocking_reason or "当前步骤需要用户介入，无法自动执行。",
                plan=self._to_plan_view(db, plan, snapshot_before),
            )

        if not self._dependencies_completed(step, self._load_steps(db, plan.id)):
            step.status = "pending"
            self._refresh_plan_state(db, plan, snapshot_before, memory_policy)
            db.commit()
            return SolveStepResponse(
                project_id=project_id,
                plan_id=plan.id,
                executed=False,
                executed_step_code=step.step_code,
                execution_status="blocked",
                message="当前步骤依赖的前置步骤尚未完成。",
                plan=self._to_plan_view(db, plan, snapshot_before),
            )

        step.status = "in_progress"
        db.flush()

        try:
            result_summary, result_payload = self._execute_step(db, project_id, step)
            step.status = "completed"
            step.result_summary = result_summary
            step.result_payload_json = json.dumps(result_payload, ensure_ascii=False)
            step.blocking_reason = None
            step.requires_user_input = False
        except ValueError as exc:
            step.status = "blocked"
            step.result_summary = str(exc)
            step.result_payload_json = json.dumps({}, ensure_ascii=False)
            step.blocking_reason = str(exc)
            step.requires_user_input = True

        snapshot_after = bid_project_agent_service.build_snapshot(db, project_id)
        memory_policy_after = project_memory_service.resolve_policy(db, project_id)
        self._reconcile_steps(db, plan, snapshot_after, memory_policy_after)
        self._refresh_plan_state(db, plan, snapshot_after, memory_policy_after)
        db.commit()

        return SolveStepResponse(
            project_id=project_id,
            plan_id=plan.id,
            executed=step.status == "completed",
            executed_step_code=step.step_code,
            execution_status=step.status,
            message=step.result_summary or "步骤执行完成。",
            plan=self._to_plan_view(db, plan, snapshot_after),
        )

    def solve(self, db: Session, project_id: str, payload: SolveRequest) -> SolveResponse:
        if payload.max_steps < 1:
            raise ValueError("max_steps must be greater than 0")
        if payload.max_steps > 20:
            raise ValueError("max_steps must be less than or equal to 20")

        plan = self._resolve_plan(db, project_id, payload.plan_id)
        if plan is None:
            created = self.create_plan(db, project_id, AgentPlanRequest())
            plan = self._resolve_plan(db, project_id, created.plan.plan_id)
            if plan is None:
                raise ValueError("Unable to initialize plan")

        executed_steps: list[SolveExecutionItem] = []
        stopped_reason = "已达到最大执行步数。"
        run_status = "partial"

        for _ in range(payload.max_steps):
            step_response = self.solve_step(
                db,
                project_id,
                SolveStepRequest(plan_id=plan.id),
            )
            executed_steps.append(
                SolveExecutionItem(
                    step_code=step_response.executed_step_code or "",
                    execution_status=step_response.execution_status,
                    message=step_response.message,
                    executed=step_response.executed,
                )
            )

            if step_response.execution_status == "blocked":
                stopped_reason = step_response.message
                run_status = "blocked"
                return SolveResponse(
                    project_id=project_id,
                    plan_id=step_response.plan_id,
                    run_status=run_status,
                    executed_steps=executed_steps,
                    stopped_reason=stopped_reason,
                    plan=step_response.plan,
                )

            if step_response.execution_status == "completed" and not step_response.executed:
                stopped_reason = step_response.message
                run_status = "completed"
                return SolveResponse(
                    project_id=project_id,
                    plan_id=step_response.plan_id,
                    run_status=run_status,
                    executed_steps=executed_steps,
                    stopped_reason=stopped_reason,
                    plan=step_response.plan,
                )

        final_plan = self.get_plan_view(db, project_id)
        if final_plan is None:
            raise ValueError("Project plan not found after solve run")
        return SolveResponse(
            project_id=project_id,
            plan_id=plan.id,
            run_status=run_status,
            executed_steps=executed_steps,
            stopped_reason=stopped_reason,
            plan=final_plan,
        )

    def _resolve_plan(self, db: Session, project_id: str, plan_id: str | None) -> ProjectPlan | None:
        if plan_id:
            return db.scalar(
                select(ProjectPlan)
                .where(ProjectPlan.id == plan_id, ProjectPlan.project_id == project_id)
                .limit(1)
            )
        return self.get_latest_plan(db, project_id)

    def _build_plan_steps(self, snapshot: ProjectStatusSnapshot, memory_policy: ProjectMemoryPolicy) -> list[PlanStepView]:
        steps: list[PlanStepView] = [
            self._make_step(
                step_code="S01",
                title="登记招标文件",
                action_name="upload_tender_documents",
                step_order=1,
                payload=PlanStepPayload(notes=["至少登记招标正文；如有附件和澄清文件一并登记。"]),
                status="completed" if snapshot.tender_document_count > 0 else "blocked",
                requires_user_input=snapshot.tender_document_count == 0,
                blocking_reason="缺少招标文件，需先登记文件。" if snapshot.tender_document_count == 0 else None,
            ),
            self._make_step(
                step_code="S02",
                title="解析招标包",
                action_name="parse_tender_package",
                step_order=2,
                payload=PlanStepPayload(force_reparse=False),
                depends_on=["S01"],
                status="completed" if snapshot.parsed_document_count > 0 and snapshot.clause_count > 0 else "pending",
            ),
            self._make_step(
                step_code="S03",
                title="生成材料清单",
                action_name="generate_checklist",
                step_order=3,
                payload=PlanStepPayload(include_recommended=True),
                depends_on=["S02"],
                status="completed" if snapshot.checklist_item_count > 0 else "pending",
            ),
            self._make_step(
                step_code="S04",
                title="补齐缺失材料",
                action_name="upload_missing_materials",
                step_order=4,
                payload=PlanStepPayload(
                    notes=self._merge_notes(
                        ["优先补齐 mandatory、risk 类材料。"],
                        ["用户曾声明资料已上传，执行前应先复核缺失清单。"] if memory_policy.user_claimed_upload_done else [],
                    )
                ),
                depends_on=["S03"],
                status="completed" if snapshot.checklist_item_count > 0 and snapshot.missing_material_count == 0 else "pending",
                requires_user_input=snapshot.checklist_item_count > 0 and snapshot.missing_material_count > 0,
                blocking_reason=(
                    f"仍缺少 {snapshot.missing_material_count} 项关键材料，需要用户上传。"
                    if snapshot.checklist_item_count > 0 and snapshot.missing_material_count > 0
                    else None
                ),
            ),
        ]

        chapter_specs = [
            ("S05", "生成资格证明文件", "C01"),
            ("S06", "生成商务响应文件", "C02"),
            ("S07", "生成报价文件", "C04"),
        ]
        for order_offset, (step_code, title, chapter_code) in enumerate(chapter_specs, start=5):
            available = chapter_code in snapshot.available_chapter_codes
            generated = chapter_code in snapshot.generated_chapter_codes
            blocked_by_memory = chapter_code == "C04" and memory_policy.defer_pricing_chapter and available
            steps.append(
                self._make_step(
                    step_code=step_code,
                    title=title,
                    action_name="generate_chapter_draft",
                    step_order=order_offset,
                    payload=PlanStepPayload(
                        chapter_codes=[chapter_code],
                        notes=["根据用户记忆约束，报价章节暂不自动生成。"] if blocked_by_memory else [],
                    ),
                    depends_on=["S04"],
                    status="completed" if generated else ("blocked" if blocked_by_memory else ("pending" if available else "skipped")),
                    requires_user_input=blocked_by_memory,
                    blocking_reason=(
                        "当前项目未识别到对应章节。"
                        if not available
                        else ("用户要求暂缓报价章节自动生成。" if blocked_by_memory else None)
                    ),
                )
            )

        compliance_checked = snapshot.project_status in {"compliance_checked", "ready_for_export"}
        steps.append(
            self._make_step(
                step_code="S08",
                title="执行基础合规检查",
                action_name="run_compliance_check",
                step_order=8,
                payload=PlanStepPayload(include_semantic_review=False),
                depends_on=["S05", "S06", "S07"],
                status="completed" if compliance_checked else "pending",
            )
        )
        steps.append(
            self._make_step(
                step_code="S09",
                title="处理高风险合规问题",
                action_name="resolve_compliance_issues",
                step_order=9,
                payload=PlanStepPayload(notes=["优先处理 fatal，其次处理 high 风险。"]),
                depends_on=["S08"],
                status="completed" if compliance_checked and snapshot.fatal_issue_count == 0 and snapshot.high_issue_count == 0 else "pending",
                requires_user_input=snapshot.fatal_issue_count > 0 or snapshot.high_issue_count > 0,
                blocking_reason=(
                    f"当前存在 {snapshot.fatal_issue_count} 个 fatal 和 {snapshot.high_issue_count} 个 high 风险问题。"
                    if snapshot.fatal_issue_count > 0 or snapshot.high_issue_count > 0
                    else None
                ),
            )
        )
        steps.append(
            self._make_step(
                step_code="S10",
                title="进入导出准备状态",
                action_name="ready_for_export",
                step_order=10,
                payload=PlanStepPayload(
                    notes=self._merge_notes(
                        ["建议先人工复核文本、材料和风险报告。"],
                        ["用户明确要求暂不导出。"] if memory_policy.defer_export else [],
                        ["用户明确要求先人工复核。"] if memory_policy.prefer_manual_review else [],
                    )
                ),
                depends_on=["S09"],
                status=(
                    "completed"
                    if snapshot.project_status == "ready_for_export"
                    else ("blocked" if memory_policy.defer_export or memory_policy.prefer_manual_review else "pending")
                ),
                requires_user_input=memory_policy.defer_export or memory_policy.prefer_manual_review,
                blocking_reason=self._export_blocking_reason(memory_policy),
            )
        )
        return steps

    def _make_step(
        self,
        step_code: str,
        title: str,
        action_name: str,
        step_order: int,
        payload: PlanStepPayload,
        status: str,
        depends_on: list[str] | None = None,
        requires_user_input: bool = False,
        blocking_reason: str | None = None,
    ) -> PlanStepView:
        return PlanStepView(
            step_code=step_code,
            step_title=title,
            action_name=action_name,
            step_order=step_order,
            status=status,
            depends_on_step_codes=depends_on or [],
            requires_user_input=requires_user_input,
            blocking_reason=blocking_reason,
            action_payload=payload,
            result_summary=None,
            result_payload={},
        )

    def _select_step(self, db: Session, plan: ProjectPlan, requested_step_code: str | None) -> PlanStep | None:
        steps = self._load_steps(db, plan.id)
        if requested_step_code:
            for step in steps:
                if step.step_code == requested_step_code:
                    return step
            raise ValueError(f"Plan step not found: {requested_step_code}")
        for step in steps:
            if step.status == "pending" and self._dependencies_completed(step, steps):
                return step
            if step.status == "blocked" and step.requires_user_input:
                return step
        return None

    def _dependencies_completed(self, step: PlanStep, steps: list[PlanStep]) -> bool:
        step_status_by_code = {item.step_code: item.status for item in steps}
        for depends_on in self._load_json_list(step.depends_on_json):
            if step_status_by_code.get(depends_on) not in {"completed", "skipped"}:
                return False
        return True

    def _execute_step(self, db: Session, project_id: str, step: PlanStep) -> tuple[str, dict]:
        payload = PlanStepPayload.model_validate_json(step.action_payload_json or "{}")
        if step.action_name == "parse_tender_package":
            response = orchestrator_service.parse_tender_package(
                db,
                project_id,
                ParseRequest(document_ids=[], force_reparse=payload.force_reparse),
            )
            return (
                f"已完成招标文件解析，共解析 {len(response.result.parsed_documents)} 份文档，提取 {len(response.result.requirements)} 个要求项。",
                {"parsed_document_count": len(response.result.parsed_documents), "requirement_count": len(response.result.requirements)},
            )
        if step.action_name == "generate_checklist":
            response = checklist_service.generate_checklist(
                db,
                project_id,
                ChecklistGenerateRequest(
                    requirement_codes=payload.requirement_codes,
                    include_recommended=payload.include_recommended,
                ),
            )
            return (
                f"已生成材料清单，共 {len(response.result.checklist_items)} 项。",
                {"checklist_item_count": len(response.result.checklist_items)},
            )
        if step.action_name == "generate_chapter_draft":
            if not payload.chapter_codes:
                raise ValueError("章节生成步骤缺少 chapter_codes")
            response = draft_service.generate_draft(
                db,
                project_id,
                DraftGenerateRequest(
                    chapter_codes=payload.chapter_codes,
                    regenerate_existing=False,
                ),
            )
            return (
                f"已生成章节 {response.result.chapter_code}《{response.result.chapter_title or ''}》草稿。",
                {
                    "chapter_code": response.result.chapter_code,
                    "generated_section_count": response.result.chapter_summary.generated_section_count,
                },
            )
        if step.action_name == "run_compliance_check":
            response = compliance_service.run_check(
                db,
                project_id,
                ComplianceCheckRequest(
                    include_semantic_review=payload.include_semantic_review,
                    rule_engine_results=[],
                ),
            )
            summary = response.result.issue_summary
            return (
                (
                    "已完成基础合规检查，"
                    f"fatal={summary.fatal}，high={summary.high}，medium={summary.medium}，low={summary.low}。"
                ),
                {
                    "overall_status": response.result.overall_status,
                    "fatal": summary.fatal,
                    "high": summary.high,
                    "medium": summary.medium,
                    "low": summary.low,
                },
            )
        if step.action_name == "ready_for_export":
            project = db.get(TenderProject, project_id)
            if project:
                project.status = "ready_for_export"
            return ("项目已进入导出准备状态。", {"project_status": "ready_for_export"})
        raise ValueError(f"当前步骤需要用户操作，不能自动执行：{step.action_name}")

    def _reconcile_steps(
        self,
        db: Session,
        plan: ProjectPlan,
        snapshot: ProjectStatusSnapshot,
        memory_policy: ProjectMemoryPolicy,
    ) -> None:
        step_by_code = {step.step_code: step for step in self._load_steps(db, plan.id)}

        self._set_step_from_snapshot(
            step_by_code.get("S01"),
            completed=snapshot.tender_document_count > 0,
            blocked=snapshot.tender_document_count == 0,
            blocking_reason="缺少招标文件，需先登记文件。",
        )
        self._set_step_from_snapshot(
            step_by_code.get("S02"),
            completed=snapshot.parsed_document_count > 0 and snapshot.clause_count > 0,
        )
        self._set_step_from_snapshot(
            step_by_code.get("S03"),
            completed=snapshot.checklist_item_count > 0,
        )
        self._set_step_from_snapshot(
            step_by_code.get("S04"),
            completed=snapshot.checklist_item_count > 0 and snapshot.missing_material_count == 0,
            blocked=snapshot.checklist_item_count > 0 and snapshot.missing_material_count > 0,
            blocking_reason=(
                f"仍缺少 {snapshot.missing_material_count} 项关键材料，需要用户上传。"
                if snapshot.checklist_item_count > 0 and snapshot.missing_material_count > 0
                else None
            ),
        )

        chapter_map = {"S05": "C01", "S06": "C02", "S07": "C04"}
        for step_code, chapter_code in chapter_map.items():
            step = step_by_code.get(step_code)
            if step is None:
                continue
            if (
                chapter_code == "C04"
                and memory_policy.defer_pricing_chapter
                and chapter_code in snapshot.available_chapter_codes
                and chapter_code not in snapshot.generated_chapter_codes
            ):
                step.status = "blocked"
                step.blocking_reason = "用户要求暂缓报价章节自动生成。"
                step.requires_user_input = True
                continue
            if chapter_code not in snapshot.available_chapter_codes:
                step.status = "skipped"
                step.blocking_reason = "当前项目未识别到对应章节。"
                step.requires_user_input = False
            elif chapter_code in snapshot.generated_chapter_codes:
                step.status = "completed"
                step.blocking_reason = None
                step.requires_user_input = False
            elif step.status != "completed":
                step.status = "pending"
                step.blocking_reason = None
                step.requires_user_input = False

        self._set_step_from_snapshot(
            step_by_code.get("S08"),
            completed=snapshot.project_status in {"compliance_checked", "ready_for_export"},
        )
        self._set_step_from_snapshot(
            step_by_code.get("S09"),
            completed=snapshot.project_status in {"compliance_checked", "ready_for_export"} and snapshot.fatal_issue_count == 0 and snapshot.high_issue_count == 0,
            blocked=snapshot.fatal_issue_count > 0 or snapshot.high_issue_count > 0,
            blocking_reason=(
                f"当前存在 {snapshot.fatal_issue_count} 个 fatal 和 {snapshot.high_issue_count} 个 high 风险问题。"
                if snapshot.fatal_issue_count > 0 or snapshot.high_issue_count > 0
                else None
            ),
        )
        self._set_step_from_snapshot(
            step_by_code.get("S10"),
            completed=snapshot.project_status == "ready_for_export",
            blocked=(memory_policy.defer_export or memory_policy.prefer_manual_review) and snapshot.project_status != "ready_for_export",
            blocking_reason=self._export_blocking_reason(memory_policy),
        )

    def _set_step_from_snapshot(
        self,
        step: PlanStep | None,
        completed: bool,
        blocked: bool = False,
        blocking_reason: str | None = None,
    ) -> None:
        if step is None:
            return
        if completed:
            step.status = "completed"
            step.requires_user_input = False
            step.blocking_reason = None
            return
        if step.status == "skipped":
            return
        if blocked:
            step.status = "blocked"
            step.requires_user_input = True
            step.blocking_reason = blocking_reason
            return
        if step.status != "completed":
            step.status = "pending"
            step.requires_user_input = False
            step.blocking_reason = None

    def _refresh_plan_state(
        self,
        db: Session,
        plan: ProjectPlan,
        snapshot: ProjectStatusSnapshot,
        memory_policy: ProjectMemoryPolicy,
    ) -> None:
        steps = self._load_steps(db, plan.id)
        current_step = next((step for step in steps if step.status in {"blocked", "pending"}), None)
        if current_step is None:
            plan.plan_status = "completed"
            plan.current_step_code = None
            plan.requires_user_input = False
            plan.blocking_reason = None
        elif current_step.status == "blocked" and current_step.requires_user_input:
            plan.plan_status = "blocked"
            plan.current_step_code = current_step.step_code
            plan.requires_user_input = True
            plan.blocking_reason = current_step.blocking_reason
        else:
            plan.plan_status = "in_progress"
            plan.current_step_code = current_step.step_code
            plan.requires_user_input = False
            plan.blocking_reason = None
        plan.overall_assessment = self._build_assessment(snapshot, memory_policy)

    def _build_assessment(self, snapshot: ProjectStatusSnapshot, memory_policy: ProjectMemoryPolicy) -> str:
        if snapshot.tender_document_count == 0:
            assessment = "项目尚未接入招标文件，当前阻塞在文档登记阶段。"
            return self._append_memory_assessment(assessment, memory_policy)
        if snapshot.parsed_document_count == 0 or snapshot.clause_count == 0:
            assessment = "已接入招标文件，但尚未形成有效解析结果。"
            return self._append_memory_assessment(assessment, memory_policy)
        if snapshot.checklist_item_count == 0:
            assessment = "解析已完成，但尚未生成投标材料清单。"
            return self._append_memory_assessment(assessment, memory_policy)
        if snapshot.missing_material_count > 0:
            assessment = f"材料清单已生成，但仍缺少 {snapshot.missing_material_count} 项关键材料。"
            return self._append_memory_assessment(assessment, memory_policy)
        if len(snapshot.generated_chapter_codes) == 0:
            assessment = "材料已基本齐备，尚未生成核心章节草稿。"
            return self._append_memory_assessment(assessment, memory_policy)
        if snapshot.project_status not in {"compliance_checked", "ready_for_export"}:
            assessment = "章节草稿已生成，但尚未完成基础合规检查。"
            return self._append_memory_assessment(assessment, memory_policy)
        if snapshot.fatal_issue_count > 0 or snapshot.high_issue_count > 0:
            assessment = f"当前存在 {snapshot.fatal_issue_count} 个 fatal 和 {snapshot.high_issue_count} 个 high 风险问题。"
            return self._append_memory_assessment(assessment, memory_policy)
        if snapshot.project_status == "ready_for_export":
            assessment = "项目已满足导出前置条件。"
            return self._append_memory_assessment(assessment, memory_policy)
        assessment = "项目已经完成主要步骤，适合进入导出准备阶段。"
        return self._append_memory_assessment(assessment, memory_policy)

    def _append_memory_assessment(self, assessment: str, memory_policy: ProjectMemoryPolicy) -> str:
        memory_notes: list[str] = []
        if memory_policy.defer_pricing_chapter:
            memory_notes.append("报价章节当前被用户记忆约束暂缓。")
        if memory_policy.defer_export:
            memory_notes.append("导出当前被用户记忆约束暂停。")
        if memory_policy.prefer_manual_review:
            memory_notes.append("进入导出前需先人工复核。")
        if not memory_notes:
            return assessment
        return f"{assessment} {' '.join(memory_notes)}"

    def _export_blocking_reason(self, memory_policy: ProjectMemoryPolicy) -> str | None:
        reasons: list[str] = []
        if memory_policy.defer_export:
            reasons.append("用户要求暂不导出")
        if memory_policy.prefer_manual_review:
            reasons.append("用户要求先人工复核")
        if not reasons:
            return None
        return "；".join(reasons) + "。"

    def _merge_notes(self, *groups: list[str]) -> list[str]:
        merged: list[str] = []
        for group in groups:
            for note in group:
                if note and note not in merged:
                    merged.append(note)
        return merged

    def _to_plan_view(self, db: Session, plan: ProjectPlan, snapshot: ProjectStatusSnapshot) -> ProjectPlanView:
        steps = self._load_steps(db, plan.id)
        return ProjectPlanView(
            plan_id=plan.id,
            project_id=plan.project_id,
            goal=plan.goal,
            plan_status=plan.plan_status,
            current_step_code=plan.current_step_code,
            overall_assessment=plan.overall_assessment,
            blocking_reason=plan.blocking_reason,
            requires_user_input=plan.requires_user_input,
            steps=[
                PlanStepView(
                    step_code=step.step_code,
                    step_title=step.step_title,
                    action_name=step.action_name,
                    step_order=step.step_order,
                    status=step.status,
                    depends_on_step_codes=self._load_json_list(step.depends_on_json),
                    requires_user_input=step.requires_user_input,
                    blocking_reason=step.blocking_reason,
                    action_payload=PlanStepPayload.model_validate_json(step.action_payload_json or "{}"),
                    result_summary=step.result_summary,
                    result_payload=self._load_json_object(step.result_payload_json),
                )
                for step in steps
            ],
            state_snapshot=snapshot,
        )

    def _load_steps(self, db: Session, plan_id: str) -> list[PlanStep]:
        return db.scalars(
            select(PlanStep).where(PlanStep.plan_id == plan_id).order_by(PlanStep.step_order.asc(), PlanStep.created_at.asc())
        ).all()

    def _load_json_list(self, value: str | None) -> list[str]:
        if not value:
            return []
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return []
        return loaded if isinstance(loaded, list) else []

    def _load_json_object(self, value: str | None) -> dict:
        if not value:
            return {}
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}


plan_and_solve_service = PlanAndSolveService()
