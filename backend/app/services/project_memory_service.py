import json
from dataclasses import dataclass, field
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import ProjectChatMessage, ProjectChatSession, ProjectMemoryItem
from app.schemas.parse import StructureTemplateRequest


@dataclass
class ProjectMemoryPolicy:
    template_mode: str | None = None
    include_technical_chapter: bool = False
    include_appendix_chapter: bool = False
    user_claimed_upload_done: bool = False
    defer_export: bool = False
    prefer_manual_review: bool = False
    defer_pricing_chapter: bool = False
    preferred_next_action: str | None = None
    active_instruction_titles: list[str] = field(default_factory=list)


class ProjectMemoryService:
    def capture_memories(self, db: Session, session: ProjectChatSession, message: ProjectChatMessage) -> None:
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
        if any(word in text for word in ("先不要导出", "不要导出", "先不导出")):
            candidates.append(
                {
                    "memory_type": "orchestration_constraint",
                    "memory_key": "defer_export",
                    "title": "用户要求暂不导出",
                    "content": text,
                    "tags": ["instruction", "export"],
                    "importance_score": 5,
                }
            )
        if any(word in text for word in ("先人工复核", "人工复核后再导出", "先人工检查", "人工检查后再导出")):
            candidates.append(
                {
                    "memory_type": "orchestration_constraint",
                    "memory_key": "prefer_manual_review",
                    "title": "用户要求先人工复核",
                    "content": text,
                    "tags": ["instruction", "review"],
                    "importance_score": 5,
                }
            )
        if any(word in text for word in ("先不要报价", "不要报价章", "先不做报价", "报价后面再说")):
            candidates.append(
                {
                    "memory_type": "orchestration_constraint",
                    "memory_key": "defer_pricing_chapter",
                    "title": "用户要求暂缓报价章节",
                    "content": text,
                    "tags": ["instruction", "pricing"],
                    "importance_score": 5,
                }
            )
        preferred_action = self._extract_preferred_action(text)
        if preferred_action:
            candidates.append(
                {
                    "memory_type": "workflow_preference",
                    "memory_key": "preferred_next_action",
                    "title": f"用户偏好优先执行 {preferred_action}",
                    "content": text,
                    "tags": ["instruction", preferred_action],
                    "importance_score": 4,
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
            self.upsert_memory(
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

    def upsert_memory(
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

    def retrieve_memories(self, db: Session, project_id: str, query: str) -> list[ProjectMemoryItem]:
        memories = self.list_active_memories(db, project_id)
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

    def list_active_memories(self, db: Session, project_id: str) -> list[ProjectMemoryItem]:
        return db.scalars(
            select(ProjectMemoryItem)
            .where(ProjectMemoryItem.project_id == project_id, ProjectMemoryItem.status == "active")
            .order_by(ProjectMemoryItem.updated_at.desc())
        ).all()

    def resolve_policy(self, db: Session, project_id: str) -> ProjectMemoryPolicy:
        policy = ProjectMemoryPolicy()
        for memory in self.list_active_memories(db, project_id):
            key = memory.memory_key
            content = memory.content or ""
            if key == "template_mode":
                if any(word in content for word in ("精简", "简洁")):
                    policy.template_mode = "compact"
                elif any(word in content for word in ("详细", "完整")):
                    policy.template_mode = "detailed"
            elif key == "include_technical_chapter":
                policy.include_technical_chapter = True
            elif key == "include_appendix_chapter":
                policy.include_appendix_chapter = True
            elif key == "user_claimed_upload_done":
                policy.user_claimed_upload_done = True
            elif key == "defer_export":
                policy.defer_export = True
                policy.active_instruction_titles.append(memory.title)
            elif key == "prefer_manual_review":
                policy.prefer_manual_review = True
                policy.active_instruction_titles.append(memory.title)
            elif key == "defer_pricing_chapter":
                policy.defer_pricing_chapter = True
                policy.active_instruction_titles.append(memory.title)
            elif key == "preferred_next_action":
                policy.preferred_next_action = self._extract_preferred_action(content)
                if memory.title:
                    policy.active_instruction_titles.append(memory.title)
        return policy

    def build_template_request_from_text(
        self,
        db: Session,
        project_id: str,
        text: str,
    ) -> StructureTemplateRequest:
        policy = self.resolve_policy(db, project_id)
        mode = policy.template_mode or "basic"
        if "精简" in text or "简洁" in text:
            mode = "compact"
        if "详细" in text or "完整" in text:
            mode = "detailed"
        include_technical = policy.include_technical_chapter or ("技术" in text)
        include_appendix = policy.include_appendix_chapter or ("附件" in text)
        return StructureTemplateRequest(
            template_mode=mode,
            include_technical_chapter=include_technical,
            include_appendix_chapter=include_appendix,
            custom_instruction=text,
            replace_existing=True,
        )

    def _extract_preferred_action(self, text: str) -> str | None:
        action_keywords = (
            ("先解析", "parse_tender_package"),
            ("先生成清单", "generate_checklist"),
            ("先补材料", "upload_missing_materials"),
            ("先生成草稿", "generate_chapter_draft"),
            ("先做合规检查", "run_compliance_check"),
            ("先处理合规问题", "resolve_compliance_issues"),
        )
        for keyword, action in action_keywords:
            if keyword in text:
                return action
        return None

    def _tokenize(self, text: str) -> list[str]:
        normalized = text.replace("，", " ").replace("。", " ").replace("：", " ").replace("、", " ")
        return [part.strip().lower() for part in normalized.split() if part.strip()]


project_memory_service = ProjectMemoryService()
