import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import ProjectChatMessage, ProjectChatSession, ProjectMemoryItem
from app.schemas.bid_agent import (
    AgentChatRequest,
    AgentChatResponse,
    BidProjectAgentDecision,
    ChatMessageItem,
    ChatSessionView,
    ProjectMemoryItemView,
    SolveRequest,
    UploadPromptItem,
)
from app.schemas.checklist import MissingChecklistItem
from app.schemas.parse import StructureTemplateRequest
from app.services.bid_project_agent_service import bid_project_agent_service
from app.services.checklist_service import checklist_service
from app.services.parse_result_service import parse_result_service
from app.services.plan_and_solve_service import plan_and_solve_service


class ChatAgentService:
    def get_or_create_session(self, db: Session, project_id: str, session_id: str | None = None) -> ProjectChatSession:
        if session_id:
            session = db.scalar(
                select(ProjectChatSession)
                .where(ProjectChatSession.id == session_id, ProjectChatSession.project_id == project_id)
                .limit(1)
            )
            if session:
                return session

        session = db.scalar(
            select(ProjectChatSession)
            .where(ProjectChatSession.project_id == project_id, ProjectChatSession.session_status == "active")
            .order_by(ProjectChatSession.created_at.desc())
            .limit(1)
        )
        if session:
            return session

        session = ProjectChatSession(
            id=str(uuid4()),
            project_id=project_id,
            title="项目对话",
            session_status="active",
            summary_text="",
            last_agent_action=None,
        )
        db.add(session)
        db.commit()
        return session

    def get_session_view(self, db: Session, project_id: str, session_id: str | None = None) -> ChatSessionView:
        session = self.get_or_create_session(db, project_id, session_id)
        return self._to_session_view(db, session)

    def chat(self, db: Session, project_id: str, payload: AgentChatRequest) -> AgentChatResponse:
        session = self.get_or_create_session(db, project_id, payload.session_id)
        user_message = self._append_message(
            db,
            session,
            role="user",
            content=payload.user_message.strip(),
            intent=self._infer_intent(payload.user_message),
            related_action=None,
            metadata={},
        )
        self._capture_memories(db, session, user_message)

        decision = bid_project_agent_service.get_next_action(db, project_id)
        retrieved_memories = self._retrieve_memories(db, project_id, payload.user_message)
        upload_prompts: list[UploadPromptItem] = []
        solve_result = None
        assistant_text = ""
        assistant_action = None

        user_intent = user_message.intent or "general"
        if user_intent in {"continue", "upload_done"} and payload.auto_execute:
            solve_result = plan_and_solve_service.solve(
                db,
                project_id,
                SolveRequest(plan_id=None, max_steps=8),
            )
            decision = bid_project_agent_service.get_next_action(db, project_id)
            assistant_text = self._format_solve_reply(solve_result, decision)
            assistant_action = decision.next_action
        elif user_intent == "regenerate_template":
            template_response = parse_result_service.generate_structure_template(
                db,
                project_id,
                self._build_template_request(payload.user_message),
                regenerated=True,
            )
            decision = bid_project_agent_service.get_next_action(db, project_id)
            assistant_text = (
                "我已经按你的要求重做了结构模板。"
                f" 当前模板模式是 {template_response.result.template_mode}。"
                " 如果模板可接受，我会继续推进下一步；如果仍不满意，可以继续告诉我想要更精简还是更完整。"
            )
            assistant_action = "regenerate_structure_template"
        elif user_intent == "status":
            assistant_text = self._format_status_reply(decision, retrieved_memories)
            assistant_action = decision.next_action
        elif user_intent == "risk":
            assistant_text = self._format_risk_reply(decision)
            assistant_action = decision.next_action
        elif user_intent == "missing_materials":
            assistant_text, upload_prompts = self._format_missing_materials_reply(db, project_id, decision)
            assistant_action = decision.next_action
        else:
            assistant_text = self._format_status_reply(decision, retrieved_memories)
            assistant_action = decision.next_action

        if decision.next_action == "upload_missing_materials" and not upload_prompts:
            _, upload_prompts = self._format_missing_materials_reply(db, project_id, decision)

        assistant_message = self._append_message(
            db,
            session,
            role="assistant",
            content=assistant_text,
            intent="assistant_reply",
            related_action=assistant_action,
            metadata={
                "next_action": decision.next_action if decision else None,
                "auto_executed": solve_result is not None,
            },
        )
        session.last_agent_action = assistant_action
        session.summary_text = self._refresh_summary(db, session)
        db.commit()

        return AgentChatResponse(
            project_id=project_id,
            session=self._to_session_view(db, session),
            assistant_message=self._to_message_item(assistant_message),
            decision=decision,
            solve_result=solve_result,
            retrieved_memories=[self._to_memory_item(item) for item in retrieved_memories],
            upload_prompts=upload_prompts,
        )

    def _append_message(
        self,
        db: Session,
        session: ProjectChatSession,
        role: str,
        content: str,
        intent: str | None,
        related_action: str | None,
        metadata: dict,
    ) -> ProjectChatMessage:
        message = ProjectChatMessage(
            id=str(uuid4()),
            session_id=session.id,
            project_id=session.project_id,
            role=role,
            content=content,
            intent=intent,
            related_action=related_action,
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
        )
        db.add(message)
        db.flush()
        return message

    def _to_session_view(self, db: Session, session: ProjectChatSession) -> ChatSessionView:
        messages = db.scalars(
            select(ProjectChatMessage)
            .where(ProjectChatMessage.session_id == session.id)
            .order_by(ProjectChatMessage.created_at.asc())
        ).all()
        return ChatSessionView(
            session_id=session.id,
            project_id=session.project_id,
            title=session.title,
            session_status=session.session_status,
            summary_text=session.summary_text,
            last_agent_action=session.last_agent_action,
            messages=[self._to_message_item(message) for message in messages],
        )

    def _to_message_item(self, message: ProjectChatMessage) -> ChatMessageItem:
        return ChatMessageItem(
            message_id=message.id,
            role=message.role,
            content=message.content,
            intent=message.intent,
            related_action=message.related_action,
            created_at=message.created_at.isoformat() if isinstance(message.created_at, datetime) else None,
        )

    def _to_memory_item(self, item: ProjectMemoryItem) -> ProjectMemoryItemView:
        tags = json.loads(item.tags_json) if item.tags_json else []
        return ProjectMemoryItemView(
            memory_id=item.id,
            memory_type=item.memory_type,
            memory_key=item.memory_key,
            title=item.title,
            content=item.content,
            tags=tags if isinstance(tags, list) else [],
            importance_score=item.importance_score,
        )

    def _infer_intent(self, text: str) -> str:
        normalized = text.strip()
        if any(word in normalized for word in ("继续", "下一步", "往下", "开始生成", "自动推进", "继续跑")):
            return "continue"
        if any(word in normalized for word in ("上传好了", "已上传", "补齐了", "传完了")):
            return "upload_done"
        if any(word in normalized for word in ("重做模板", "模板不满意", "目录不满意", "重新生成模板", "重新做模板")):
            return "regenerate_template"
        if any(word in normalized for word in ("风险", "问题", "废标")):
            return "risk"
        if any(word in normalized for word in ("缺什么", "缺材料", "还差什么")):
            return "missing_materials"
        if any(word in normalized for word in ("现在什么情况", "当前状态", "进展", "到哪一步")):
            return "status"
        return "general"

    def _capture_memories(self, db: Session, session: ProjectChatSession, message: ProjectChatMessage) -> None:
        text = message.content.strip()
        candidates: list[dict[str, object]] = []

        if any(word in text for word in ("精简", "简洁")):
            candidates.append(
                {
                    "memory_type": "template_preference",
                    "memory_key": "template_mode",
                    "title": "用户偏好精简模板",
                    "content": text,
                    "tags": ["template", "compact"],
                    "importance_score": 4,
                }
            )
        if any(word in text for word in ("详细", "完整")):
            candidates.append(
                {
                    "memory_type": "template_preference",
                    "memory_key": "template_mode",
                    "title": "用户偏好详细模板",
                    "content": text,
                    "tags": ["template", "detailed"],
                    "importance_score": 4,
                }
            )
        if any(word in text for word in ("技术章节", "加技术")):
            candidates.append(
                {
                    "memory_type": "template_preference",
                    "memory_key": "include_technical_chapter",
                    "title": "用户要求加入技术章节",
                    "content": text,
                    "tags": ["template", "technical"],
                    "importance_score": 3,
                }
            )
        if any(word in text for word in ("附件", "补充材料")):
            candidates.append(
                {
                    "memory_type": "template_preference",
                    "memory_key": "include_appendix_chapter",
                    "title": "用户要求加入附件章节",
                    "content": text,
                    "tags": ["template", "appendix"],
                    "importance_score": 3,
                }
            )
        if any(word in text for word in ("上传好了", "已上传", "补齐了", "传完了")):
            candidates.append(
                {
                    "memory_type": "workflow_update",
                    "memory_key": "user_claimed_upload_done",
                    "title": "用户声明已上传资料",
                    "content": text,
                    "tags": ["materials", "upload"],
                    "importance_score": 3,
                }
            )
        if any(word in text for word in ("不要", "优先", "先做", "先不要")):
            candidates.append(
                {
                    "memory_type": "user_instruction",
                    "memory_key": f"user_instruction:{uuid4().hex[:8]}",
                    "title": "用户流程指令",
                    "content": text,
                    "tags": ["instruction"],
                    "importance_score": 2,
                }
            )

        for candidate in candidates:
            self._upsert_memory(
                db,
                project_id=session.project_id,
                session_id=session.id,
                source_message_id=message.id,
                memory_type=str(candidate["memory_type"]),
                memory_key=str(candidate["memory_key"]),
                title=str(candidate["title"]),
                content=str(candidate["content"]),
                tags=list(candidate["tags"]),
                importance_score=int(candidate["importance_score"]),
            )

    def _upsert_memory(
        self,
        db: Session,
        project_id: str,
        session_id: str,
        source_message_id: str,
        memory_type: str,
        memory_key: str,
        title: str,
        content: str,
        tags: list[str],
        importance_score: int,
    ) -> None:
        existing = db.scalar(
            select(ProjectMemoryItem)
            .where(
                ProjectMemoryItem.project_id == project_id,
                ProjectMemoryItem.memory_key == memory_key,
                ProjectMemoryItem.status == "active",
            )
            .limit(1)
        )
        if existing:
            existing.session_id = session_id
            existing.title = title
            existing.content = content
            existing.tags_json = json.dumps(tags, ensure_ascii=False)
            existing.source_message_id = source_message_id
            existing.importance_score = importance_score
            return

        db.add(
            ProjectMemoryItem(
                id=str(uuid4()),
                project_id=project_id,
                session_id=session_id,
                memory_type=memory_type,
                memory_key=memory_key,
                title=title,
                content=content,
                tags_json=json.dumps(tags, ensure_ascii=False),
                source_message_id=source_message_id,
                importance_score=importance_score,
                status="active",
            )
        )

    def _retrieve_memories(self, db: Session, project_id: str, query: str) -> list[ProjectMemoryItem]:
        memories = db.scalars(
            select(ProjectMemoryItem)
            .where(ProjectMemoryItem.project_id == project_id, ProjectMemoryItem.status == "active")
            .order_by(ProjectMemoryItem.updated_at.desc())
        ).all()
        query_terms = {term for term in self._tokenize(query) if len(term) > 1}
        scored: list[tuple[int, ProjectMemoryItem]] = []
        for memory in memories:
            tags = json.loads(memory.tags_json) if memory.tags_json else []
            haystack = f"{memory.title} {memory.content} {' '.join(tags if isinstance(tags, list) else [])}"
            score = memory.importance_score
            for term in query_terms:
                if term in haystack:
                    score += 2
            if not query_terms and memory.importance_score >= 3:
                score += 1
            scored.append((score, memory))
        scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        return [memory for score, memory in scored[:5] if score > 0]

    def _tokenize(self, text: str) -> list[str]:
        normalized = text.replace("，", " ").replace("。", " ").replace("：", " ").replace("、", " ")
        return [part.strip().lower() for part in normalized.split() if part.strip()]

    def _build_template_request(self, text: str) -> StructureTemplateRequest:
        mode = "basic"
        if "精简" in text or "简洁" in text:
            mode = "compact"
        if "详细" in text or "完整" in text:
            mode = "detailed"
        return StructureTemplateRequest(
            template_mode=mode,
            include_technical_chapter=("技术" in text),
            include_appendix_chapter=("附件" in text),
            custom_instruction=text,
            replace_existing=True,
        )

    def _format_status_reply(self, decision: BidProjectAgentDecision, memories: list[ProjectMemoryItem]) -> str:
        memory_hint = ""
        if memories:
            memory_titles = "；".join(item.title for item in memories[:3])
            memory_hint = f" 我记得的关键信息包括：{memory_titles}。"
        return (
            f"{decision.current_assessment}"
            f" 下一步我建议执行“{decision.next_action}”。"
            f" 原因是：{decision.reason}"
            f"{memory_hint}"
        )

    def _format_risk_reply(self, decision: BidProjectAgentDecision) -> str:
        snapshot = decision.state_snapshot
        return (
            f"当前项目的高风险概况是：fatal {snapshot.fatal_issue_count} 个，high {snapshot.high_issue_count} 个。"
            f" 当前最合理的动作仍然是“{decision.next_action}”。"
        )

    def _format_missing_materials_reply(
        self,
        db: Session,
        project_id: str,
        decision: BidProjectAgentDecision,
    ) -> tuple[str, list[UploadPromptItem]]:
        snapshot = decision.state_snapshot
        if snapshot.missing_material_count == 0:
            return "当前没有缺失材料，可以继续推进章节生成或合规检查。", []

        missing_response = checklist_service.get_missing_checklist(db, project_id)
        prompts = [self._build_upload_prompt(item) for item in missing_response.missing_items[:5]]
        summary = "；".join(prompt.prompt_text for prompt in prompts[:3])
        return (
            f"当前还缺少 {snapshot.missing_material_count} 项关键材料。"
            f" 请按顺序处理：{summary}"
            " 每上传一项后，可以直接回复我“已上传”。",
            prompts,
        )

    def _build_upload_prompt(self, item: MissingChecklistItem) -> UploadPromptItem:
        return UploadPromptItem(
            material_code=item.material_code,
            material_type=item.material_type,
            material_name=item.material_name,
            submission_category=item.submission_category,
            prompt_text=f"请先上传 {item.material_name}（{item.material_type}）。",
        )

    def _format_solve_reply(self, solve_result, decision: BidProjectAgentDecision) -> str:
        if solve_result.run_status == "blocked":
            return (
                "我已经自动推进了当前项目，但现在需要你介入。"
                f" 停止原因：{solve_result.stopped_reason}"
            )
        if solve_result.run_status == "completed":
            return "我已经把当前可自动执行的步骤推进完了。项目现在可以进入人工复核或导出准备阶段。"
        return (
            "我已经自动执行了一部分步骤。"
            f" 当前停止原因：{solve_result.stopped_reason}"
            f" 接下来建议执行“{decision.next_action}”。"
        )

    def _refresh_summary(self, db: Session, session: ProjectChatSession) -> str:
        messages = db.scalars(
            select(ProjectChatMessage)
            .where(ProjectChatMessage.session_id == session.id)
            .order_by(ProjectChatMessage.created_at.desc())
            .limit(8)
        ).all()
        lines = [f"{message.role}:{message.content[:80]}" for message in reversed(messages)]
        return "\n".join(lines)


chat_agent_service = ChatAgentService()
