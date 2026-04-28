import json
from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.domain import AgentMessage, AgentTask
from app.schemas.bid_agent import (
    AgentChatResponse,
    AgentCoordinationTrace,
    AgentMessageView,
    AgentPlanRequest,
    AgentPlanResponse,
    AgentTaskView,
    BidProjectAgentDecision,
    SolveRequest,
    SolveResponse,
    SolveStepRequest,
    SolveStepResponse,
)
from app.services.bid_project_agent_service import bid_project_agent_service
from app.services.plan_and_solve_service import plan_and_solve_service
from app.services.project_memory_service import project_memory_service


class MultiAgentService:
    def _emit(self, progress_callback: Callable[[str, dict], None] | None, event: str, data: dict) -> None:
        if progress_callback is not None:
            progress_callback(event, data)

    def coordinate_next_action(
        self,
        db: Session,
        project_id: str,
        session_id: str | None = None,
        progress_callback: Callable[[str, dict], None] | None = None,
    ) -> BidProjectAgentDecision:
        root_task = self._create_task(
            db,
            project_id=project_id,
            session_id=session_id,
            agent_name="coordinator_agent",
            task_type="coordinate_next_action",
            assigned_by="api_gateway",
            input_payload={},
            progress_callback=progress_callback,
        )
        self._post_message(
            db,
            project_id=project_id,
            session_id=session_id,
            task_id=root_task.id,
            from_agent="coordinator_agent",
            to_agent="memory_agent",
            message_type="memory_policy_request",
            content="读取项目级记忆约束，为下一步动作决策提供上下文。",
            payload={},
            progress_callback=progress_callback,
        )
        memory_task = self._create_task(
            db,
            project_id=project_id,
            session_id=session_id,
            parent_task_id=root_task.id,
            agent_name="memory_agent",
            task_type="resolve_memory_policy",
            assigned_by="coordinator_agent",
            input_payload={},
            progress_callback=progress_callback,
        )
        memory_policy = project_memory_service.resolve_policy(db, project_id)
        self._complete_task(memory_task, memory_policy.__dict__, progress_callback=progress_callback)
        self._post_message(
            db,
            project_id=project_id,
            session_id=session_id,
            task_id=memory_task.id,
            from_agent="memory_agent",
            to_agent="planning_agent",
            message_type="memory_policy_ready",
            content="项目级 memory policy 已解析完成。",
            payload=memory_policy.__dict__,
            progress_callback=progress_callback,
        )

        planning_task = self._create_task(
            db,
            project_id=project_id,
            session_id=session_id,
            parent_task_id=root_task.id,
            depends_on_task_id=memory_task.id,
            agent_name="planning_agent",
            task_type="decide_next_action",
            assigned_by="coordinator_agent",
            input_payload={"memory_policy_applied": True},
            progress_callback=progress_callback,
        )
        decision = bid_project_agent_service.get_next_action(db, project_id)
        self._complete_task(planning_task, decision.model_dump(mode="json"), progress_callback=progress_callback)
        self._post_message(
            db,
            project_id=project_id,
            session_id=session_id,
            task_id=planning_task.id,
            from_agent="planning_agent",
            to_agent="coordinator_agent",
            message_type="next_action_ready",
            content=f"已生成下一步动作：{decision.next_action}。",
            payload={"next_action": decision.next_action},
            progress_callback=progress_callback,
        )
        self._complete_task(
            root_task,
            {"status": "completed", "next_action": decision.next_action},
            progress_callback=progress_callback,
        )
        db.commit()
        return decision.model_copy(update={"coordination_trace": self._build_trace(db, root_task.id)})

    def coordinate_plan(
        self,
        db: Session,
        project_id: str,
        payload: AgentPlanRequest,
        session_id: str | None = None,
        progress_callback: Callable[[str, dict], None] | None = None,
    ) -> AgentPlanResponse:
        root_task = self._create_task(
            db,
            project_id=project_id,
            session_id=session_id,
            agent_name="coordinator_agent",
            task_type="coordinate_plan",
            assigned_by="api_gateway",
            input_payload=payload.model_dump(mode="json"),
            progress_callback=progress_callback,
        )
        memory_task = self._create_and_run_memory_task(db, project_id, session_id, root_task.id, progress_callback)
        planning_task = self._create_task(
            db,
            project_id=project_id,
            session_id=session_id,
            parent_task_id=root_task.id,
            depends_on_task_id=memory_task.id,
            agent_name="planning_agent",
            task_type="create_project_plan",
            assigned_by="coordinator_agent",
            input_payload=payload.model_dump(mode="json"),
            progress_callback=progress_callback,
        )
        response = plan_and_solve_service.create_plan(db, project_id, payload)
        self._complete_task(planning_task, response.model_dump(mode="json"), progress_callback=progress_callback)
        self._post_message(
            db,
            project_id=project_id,
            session_id=session_id,
            task_id=planning_task.id,
            from_agent="planning_agent",
            to_agent="coordinator_agent",
            message_type="plan_ready",
            content="项目计划已生成。",
            payload={"plan_id": response.plan.plan_id, "current_step_code": response.plan.current_step_code},
            progress_callback=progress_callback,
        )
        self._complete_task(
            root_task,
            {"status": "completed", "plan_id": response.plan.plan_id},
            progress_callback=progress_callback,
        )
        db.commit()
        return response.model_copy(update={"coordination_trace": self._build_trace(db, root_task.id)})

    def coordinate_solve_step(
        self,
        db: Session,
        project_id: str,
        payload: SolveStepRequest,
        session_id: str | None = None,
        progress_callback: Callable[[str, dict], None] | None = None,
    ) -> SolveStepResponse:
        root_task = self._create_task(
            db,
            project_id=project_id,
            session_id=session_id,
            agent_name="coordinator_agent",
            task_type="coordinate_solve_step",
            assigned_by="api_gateway",
            input_payload=payload.model_dump(mode="json"),
            progress_callback=progress_callback,
        )
        memory_task = self._create_and_run_memory_task(db, project_id, session_id, root_task.id, progress_callback)
        execution_task = self._create_task(
            db,
            project_id=project_id,
            session_id=session_id,
            parent_task_id=root_task.id,
            depends_on_task_id=memory_task.id,
            agent_name="execution_agent",
            task_type="solve_plan_step",
            assigned_by="coordinator_agent",
            input_payload=payload.model_dump(mode="json"),
            progress_callback=progress_callback,
        )
        response = plan_and_solve_service.solve_step(db, project_id, payload)
        self._complete_task(execution_task, response.model_dump(mode="json"), progress_callback=progress_callback)
        self._post_message(
            db,
            project_id=project_id,
            session_id=session_id,
            task_id=execution_task.id,
            from_agent="execution_agent",
            to_agent="coordinator_agent",
            message_type="step_result",
            content=response.message,
            payload={
                "executed_step_code": response.executed_step_code,
                "execution_status": response.execution_status,
            },
            progress_callback=progress_callback,
        )
        self._maybe_run_compliance_agent(
            db,
            project_id=project_id,
            session_id=session_id,
            root_task_id=root_task.id,
            response=response,
            progress_callback=progress_callback,
        )
        self._complete_task(
            root_task,
            {"status": response.execution_status, "step_code": response.executed_step_code},
            progress_callback=progress_callback,
        )
        db.commit()
        return response.model_copy(update={"coordination_trace": self._build_trace(db, root_task.id)})

    def coordinate_solve(
        self,
        db: Session,
        project_id: str,
        payload: SolveRequest,
        session_id: str | None = None,
        progress_callback: Callable[[str, dict], None] | None = None,
    ) -> SolveResponse:
        root_task = self._create_task(
            db,
            project_id=project_id,
            session_id=session_id,
            agent_name="coordinator_agent",
            task_type="coordinate_solve",
            assigned_by="api_gateway",
            input_payload=payload.model_dump(mode="json"),
            progress_callback=progress_callback,
        )
        memory_task = self._create_and_run_memory_task(db, project_id, session_id, root_task.id, progress_callback)
        execution_task = self._create_task(
            db,
            project_id=project_id,
            session_id=session_id,
            parent_task_id=root_task.id,
            depends_on_task_id=memory_task.id,
            agent_name="execution_agent",
            task_type="solve_plan",
            assigned_by="coordinator_agent",
            input_payload=payload.model_dump(mode="json"),
            progress_callback=progress_callback,
        )
        response = plan_and_solve_service.solve(db, project_id, payload)
        self._complete_task(execution_task, response.model_dump(mode="json"), progress_callback=progress_callback)
        self._post_message(
            db,
            project_id=project_id,
            session_id=session_id,
            task_id=execution_task.id,
            from_agent="execution_agent",
            to_agent="coordinator_agent",
            message_type="solve_result",
            content=response.stopped_reason,
            payload={"run_status": response.run_status, "plan_id": response.plan_id},
            progress_callback=progress_callback,
        )
        self._maybe_run_compliance_agent_for_solve(
            db,
            project_id=project_id,
            session_id=session_id,
            root_task_id=root_task.id,
            response=response,
            progress_callback=progress_callback,
        )
        self._complete_task(
            root_task,
            {"status": response.run_status, "plan_id": response.plan_id},
            progress_callback=progress_callback,
        )
        db.commit()
        return response.model_copy(update={"coordination_trace": self._build_trace(db, root_task.id)})

    def attach_trace_to_chat(
        self,
        db: Session,
        response: AgentChatResponse,
    ) -> AgentChatResponse:
        trace = None
        if response.solve_result and response.solve_result.coordination_trace:
            trace = response.solve_result.coordination_trace
        return response.model_copy(update={"coordination_trace": trace})

    def list_tasks(self, db: Session, project_id: str, session_id: str | None = None) -> list[AgentTaskView]:
        stmt = select(AgentTask).where(AgentTask.project_id == project_id).order_by(AgentTask.created_at.desc())
        if session_id:
            stmt = stmt.where(AgentTask.session_id == session_id)
        return [self._to_task_view(task) for task in db.scalars(stmt.limit(100)).all()]

    def list_messages(self, db: Session, project_id: str, session_id: str | None = None) -> list[AgentMessageView]:
        stmt = select(AgentMessage).where(AgentMessage.project_id == project_id).order_by(AgentMessage.created_at.desc())
        if session_id:
            stmt = stmt.where(AgentMessage.session_id == session_id)
        return [self._to_message_view(message) for message in db.scalars(stmt.limit(200)).all()]

    def _create_and_run_memory_task(
        self,
        db: Session,
        project_id: str,
        session_id: str | None,
        root_task_id: str,
        progress_callback: Callable[[str, dict], None] | None = None,
    ) -> AgentTask:
        self._post_message(
            db,
            project_id=project_id,
            session_id=session_id,
            task_id=root_task_id,
            from_agent="coordinator_agent",
            to_agent="memory_agent",
            message_type="memory_policy_request",
            content="协调前先读取项目级 memory policy。",
            payload={},
            progress_callback=progress_callback,
        )
        task = self._create_task(
            db,
            project_id=project_id,
            session_id=session_id,
            parent_task_id=root_task_id,
            agent_name="memory_agent",
            task_type="resolve_memory_policy",
            assigned_by="coordinator_agent",
            input_payload={},
            progress_callback=progress_callback,
        )
        memory_policy = project_memory_service.resolve_policy(db, project_id)
        self._complete_task(task, memory_policy.__dict__, progress_callback=progress_callback)
        return task

    def _maybe_run_compliance_agent(
        self,
        db: Session,
        project_id: str,
        session_id: str | None,
        root_task_id: str,
        response: SolveStepResponse,
        progress_callback: Callable[[str, dict], None] | None = None,
    ) -> None:
        action_name = self._resolve_action_name(response.plan, response.executed_step_code)
        if action_name not in {"run_compliance_check", "resolve_compliance_issues"}:
            return
        compliance_task = self._create_task(
            db,
            project_id=project_id,
            session_id=session_id,
            parent_task_id=root_task_id,
            agent_name="compliance_agent",
            task_type="review_compliance_state",
            assigned_by="coordinator_agent",
            input_payload={
                "executed_step_code": response.executed_step_code,
                "execution_status": response.execution_status,
            },
            progress_callback=progress_callback,
        )
        snapshot = response.plan.state_snapshot
        output = {
            "fatal_issue_count": snapshot.fatal_issue_count,
            "high_issue_count": snapshot.high_issue_count,
            "plan_status": response.plan.plan_status,
        }
        self._complete_task(compliance_task, output, progress_callback=progress_callback)
        self._post_message(
            db,
            project_id=project_id,
            session_id=session_id,
            task_id=compliance_task.id,
            from_agent="compliance_agent",
            to_agent="coordinator_agent",
            message_type="compliance_summary",
            content="合规状态已复核。",
            payload=output,
            progress_callback=progress_callback,
        )

    def _maybe_run_compliance_agent_for_solve(
        self,
        db: Session,
        project_id: str,
        session_id: str | None,
        root_task_id: str,
        response: SolveResponse,
        progress_callback: Callable[[str, dict], None] | None = None,
    ) -> None:
        if not any(step.step_code == "S08" for step in response.plan.steps):
            return
        snapshot = response.plan.state_snapshot
        if snapshot.compliance_issue_count == 0 and snapshot.fatal_issue_count == 0 and snapshot.high_issue_count == 0:
            return
        compliance_task = self._create_task(
            db,
            project_id=project_id,
            session_id=session_id,
            parent_task_id=root_task_id,
            agent_name="compliance_agent",
            task_type="review_compliance_state",
            assigned_by="coordinator_agent",
            input_payload={"run_status": response.run_status},
            progress_callback=progress_callback,
        )
        output = {
            "compliance_issue_count": snapshot.compliance_issue_count,
            "fatal_issue_count": snapshot.fatal_issue_count,
            "high_issue_count": snapshot.high_issue_count,
        }
        self._complete_task(compliance_task, output, progress_callback=progress_callback)
        self._post_message(
            db,
            project_id=project_id,
            session_id=session_id,
            task_id=compliance_task.id,
            from_agent="compliance_agent",
            to_agent="coordinator_agent",
            message_type="compliance_summary",
            content="求解后合规状态已复核。",
            payload=output,
            progress_callback=progress_callback,
        )

    def _resolve_action_name(self, plan, step_code: str | None) -> str | None:
        if not step_code:
            return None
        for step in plan.steps:
            if step.step_code == step_code:
                return step.action_name
        return None

    def _create_task(
        self,
        db: Session,
        project_id: str,
        session_id: str | None,
        agent_name: str,
        task_type: str,
        assigned_by: str,
        input_payload: dict,
        parent_task_id: str | None = None,
        depends_on_task_id: str | None = None,
        progress_callback: Callable[[str, dict], None] | None = None,
    ) -> AgentTask:
        task = AgentTask(
            id=str(uuid4()),
            project_id=project_id,
            session_id=session_id,
            parent_task_id=parent_task_id,
            depends_on_task_id=depends_on_task_id,
            agent_name=agent_name,
            task_type=task_type,
            assigned_by=assigned_by,
            input_json=json.dumps(input_payload, ensure_ascii=False),
            output_json=None,
            task_status="running",
            blocking_reason=None,
        )
        db.add(task)
        db.flush()
        self._emit(
            progress_callback,
            "task_update",
            {
                "task_id": task.id,
                "agent_name": task.agent_name,
                "task_type": task.task_type,
                "task_status": task.task_status,
                "parent_task_id": task.parent_task_id,
                "depends_on_task_id": task.depends_on_task_id,
            },
        )
        return task

    def _complete_task(
        self,
        task: AgentTask,
        output_payload: dict,
        task_status: str = "completed",
        progress_callback: Callable[[str, dict], None] | None = None,
    ) -> None:
        task.output_json = json.dumps(output_payload, ensure_ascii=False)
        task.task_status = task_status
        task.blocking_reason = None if task_status == "completed" else task.blocking_reason
        self._emit(
            progress_callback,
            "task_update",
            {
                "task_id": task.id,
                "agent_name": task.agent_name,
                "task_type": task.task_type,
                "task_status": task.task_status,
                "output": output_payload,
            },
        )

    def _post_message(
        self,
        db: Session,
        project_id: str,
        session_id: str | None,
        task_id: str | None,
        from_agent: str,
        to_agent: str,
        message_type: str,
        content: str,
        payload: dict,
        progress_callback: Callable[[str, dict], None] | None = None,
    ) -> AgentMessage:
        message = AgentMessage(
            id=str(uuid4()),
            project_id=project_id,
            session_id=session_id,
            task_id=task_id,
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            content=content,
            payload_json=json.dumps(payload, ensure_ascii=False),
            delivery_status="delivered",
        )
        db.add(message)
        db.flush()
        self._emit(
            progress_callback,
            "agent_message",
            {
                "message_id": message.id,
                "task_id": message.task_id,
                "from_agent": from_agent,
                "to_agent": to_agent,
                "message_type": message_type,
                "content": content,
                "payload": payload,
            },
        )
        return message

    def _build_trace(self, db: Session, root_task_id: str) -> AgentCoordinationTrace:
        tasks = db.scalars(
            select(AgentTask)
            .where(or_(AgentTask.id == root_task_id, AgentTask.parent_task_id == root_task_id))
            .order_by(AgentTask.created_at.asc())
        ).all()
        task_ids = [task.id for task in tasks]
        messages = db.scalars(
            select(AgentMessage)
            .where(AgentMessage.task_id.in_(task_ids))
            .order_by(AgentMessage.created_at.asc())
        ).all()
        return AgentCoordinationTrace(
            root_task_id=root_task_id,
            tasks=[self._to_task_view(task) for task in tasks],
            messages=[self._to_message_view(message) for message in messages],
        )

    def _to_task_view(self, task: AgentTask) -> AgentTaskView:
        return AgentTaskView(
            task_id=task.id,
            project_id=task.project_id,
            session_id=task.session_id,
            parent_task_id=task.parent_task_id,
            depends_on_task_id=task.depends_on_task_id,
            agent_name=task.agent_name,
            task_type=task.task_type,
            assigned_by=task.assigned_by,
            task_status=task.task_status,
            blocking_reason=task.blocking_reason,
            input_json=task.input_json,
            output_json=task.output_json,
            created_at=task.created_at.isoformat() if isinstance(task.created_at, datetime) else None,
        )

    def _to_message_view(self, message: AgentMessage) -> AgentMessageView:
        return AgentMessageView(
            message_id=message.id,
            project_id=message.project_id,
            session_id=message.session_id,
            task_id=message.task_id,
            from_agent=message.from_agent,
            to_agent=message.to_agent,
            message_type=message.message_type,
            content=message.content,
            payload_json=message.payload_json,
            delivery_status=message.delivery_status,
            created_at=message.created_at.isoformat() if isinstance(message.created_at, datetime) else None,
        )


multi_agent_service = MultiAgentService()
