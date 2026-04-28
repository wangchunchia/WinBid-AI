from pydantic import Field

from app.schemas.common import SchemaBase


class ProjectStatusSnapshot(SchemaBase):
    project_id: str
    project_status: str
    tender_document_count: int = 0
    parsed_document_count: int = 0
    clause_count: int = 0
    requirement_count: int = 0
    checklist_item_count: int = 0
    missing_material_count: int = 0
    uploaded_material_count: int = 0
    draft_chapter_count: int = 0
    generated_draft_chapter_count: int = 0
    compliance_issue_count: int = 0
    fatal_issue_count: int = 0
    high_issue_count: int = 0
    available_chapter_codes: list[str] = Field(default_factory=list)
    generated_chapter_codes: list[str] = Field(default_factory=list)
    missing_material_types: list[str] = Field(default_factory=list)
    fatal_issue_codes: list[str] = Field(default_factory=list)
    high_issue_codes: list[str] = Field(default_factory=list)


class AgentActionPayload(SchemaBase):
    endpoint: str | None = None
    method: str | None = None
    chapter_codes: list[str] = Field(default_factory=list)
    missing_material_types: list[str] = Field(default_factory=list)
    blocking_issue_codes: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AgentTaskView(SchemaBase):
    task_id: str
    project_id: str
    session_id: str | None = None
    parent_task_id: str | None = None
    depends_on_task_id: str | None = None
    agent_name: str
    task_type: str
    assigned_by: str | None = None
    task_status: str
    blocking_reason: str | None = None
    input_json: str | None = None
    output_json: str | None = None
    created_at: str | None = None


class AgentMessageView(SchemaBase):
    message_id: str
    project_id: str
    session_id: str | None = None
    task_id: str | None = None
    from_agent: str
    to_agent: str
    message_type: str
    content: str
    payload_json: str | None = None
    delivery_status: str
    created_at: str | None = None


class AgentCoordinationTrace(SchemaBase):
    root_task_id: str
    tasks: list[AgentTaskView] = Field(default_factory=list)
    messages: list[AgentMessageView] = Field(default_factory=list)


class BidProjectAgentDecision(SchemaBase):
    project_id: str
    agent_mode: str
    current_assessment: str
    next_action: str
    reason: str
    requires_user_input: bool
    confidence: float
    action_payload: AgentActionPayload
    state_snapshot: ProjectStatusSnapshot
    coordination_trace: AgentCoordinationTrace | None = None


class PlanStepPayload(SchemaBase):
    chapter_codes: list[str] = Field(default_factory=list)
    requirement_codes: list[str] = Field(default_factory=list)
    include_recommended: bool = True
    force_reparse: bool = False
    include_semantic_review: bool = False
    notes: list[str] = Field(default_factory=list)


class PlanStepView(SchemaBase):
    step_code: str
    step_title: str
    action_name: str
    step_order: int
    status: str
    depends_on_step_codes: list[str] = Field(default_factory=list)
    requires_user_input: bool = False
    blocking_reason: str | None = None
    action_payload: PlanStepPayload
    result_summary: str | None = None
    result_payload: dict = Field(default_factory=dict)


class ProjectPlanView(SchemaBase):
    plan_id: str
    project_id: str
    goal: str
    plan_status: str
    current_step_code: str | None = None
    overall_assessment: str | None = None
    blocking_reason: str | None = None
    requires_user_input: bool = False
    steps: list[PlanStepView] = Field(default_factory=list)
    state_snapshot: ProjectStatusSnapshot


class AgentPlanRequest(SchemaBase):
    goal: str = "完成可审阅的投标文件草稿并通过基础合规检查"
    refresh_existing: bool = True


class AgentPlanResponse(SchemaBase):
    project_id: str
    planner_mode: str
    plan: ProjectPlanView
    coordination_trace: AgentCoordinationTrace | None = None


class SolveStepRequest(SchemaBase):
    plan_id: str | None = None
    step_code: str | None = None


class SolveStepResponse(SchemaBase):
    project_id: str
    plan_id: str
    executed: bool
    executed_step_code: str | None = None
    execution_status: str
    message: str
    plan: ProjectPlanView
    coordination_trace: AgentCoordinationTrace | None = None


class SolveRequest(SchemaBase):
    plan_id: str | None = None
    max_steps: int = 5


class SolveExecutionItem(SchemaBase):
    step_code: str
    execution_status: str
    message: str
    executed: bool


class SolveResponse(SchemaBase):
    project_id: str
    plan_id: str
    run_status: str
    executed_steps: list[SolveExecutionItem] = Field(default_factory=list)
    stopped_reason: str
    plan: ProjectPlanView
    coordination_trace: AgentCoordinationTrace | None = None


class ChatMessageItem(SchemaBase):
    message_id: str
    role: str
    content: str
    intent: str | None = None
    related_action: str | None = None
    created_at: str | None = None


class ProjectMemoryItemView(SchemaBase):
    memory_id: str
    memory_type: str
    memory_key: str
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)
    importance_score: int = 1


class UploadPromptItem(SchemaBase):
    material_code: str
    material_type: str
    material_name: str
    submission_category: str
    prompt_text: str


class ChatSessionView(SchemaBase):
    session_id: str
    project_id: str
    title: str
    session_status: str
    summary_text: str | None = None
    last_agent_action: str | None = None
    messages: list[ChatMessageItem] = Field(default_factory=list)


class AgentChatRequest(SchemaBase):
    session_id: str | None = None
    user_message: str
    auto_execute: bool = True


class AgentChatResponse(SchemaBase):
    project_id: str
    session: ChatSessionView
    assistant_message: ChatMessageItem
    decision: BidProjectAgentDecision | None = None
    solve_result: SolveResponse | None = None
    retrieved_memories: list[ProjectMemoryItemView] = Field(default_factory=list)
    upload_prompts: list[UploadPromptItem] = Field(default_factory=list)
    coordination_trace: AgentCoordinationTrace | None = None


class AgentStreamStartResponse(SchemaBase):
    project_id: str
    stream_id: str
    stream_url: str
    status: str = "started"
