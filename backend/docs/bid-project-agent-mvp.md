# Bid Project Agent MVP

## Goal

Add a lightweight project-level agent that can examine the current bid project state and decide the single best next action.

This layer sits above the existing workflow endpoints and makes the system feel agentic without replacing the deterministic backend.

## Position in the System

The existing backend already has execution tools:

1. Tender document registration
2. Tender parsing
3. Checklist generation
4. Material upload
5. Draft generation
6. Compliance checking
7. Export

The `Bid Project Agent` does not replace these tools. It decides which one should be used next.

## MVP Scope

The MVP agent:

1. Reads a project state snapshot from the database.
2. Chooses one next action from a constrained action set.
3. Returns a structured explanation and suggested endpoint.
4. Supports heuristic fallback by default.
5. Supports optional LLM-based decision mode when OpenAI config is enabled.

## Action Set

The agent can choose only one of these actions:

1. `upload_tender_documents`
2. `parse_tender_package`
3. `generate_checklist`
4. `upload_missing_materials`
5. `generate_chapter_draft`
6. `run_compliance_check`
7. `resolve_compliance_issues`
8. `ready_for_export`

## State Input Schema

```json
{
  "project_id": "string",
  "project_status": "string",
  "tender_document_count": 0,
  "parsed_document_count": 0,
  "clause_count": 0,
  "requirement_count": 0,
  "checklist_item_count": 0,
  "missing_material_count": 0,
  "uploaded_material_count": 0,
  "draft_chapter_count": 0,
  "generated_draft_chapter_count": 0,
  "compliance_issue_count": 0,
  "fatal_issue_count": 0,
  "high_issue_count": 0
}
```

## Decision Output Schema

```json
{
  "project_id": "string",
  "agent_mode": "heuristic|llm",
  "current_assessment": "string",
  "next_action": "string",
  "reason": "string",
  "requires_user_input": true,
  "confidence": 0.95,
  "action_payload": {
    "endpoint": "/api/v1/projects/{id}/...",
    "method": "GET|POST",
    "chapter_codes": [],
    "missing_material_types": [],
    "blocking_issue_codes": [],
    "notes": []
  },
  "state_snapshot": {}
}
```

## Prompt

The optional LLM decision mode uses this decision frame:

```text
你是自动写标书系统的项目总控 Agent。

你的任务是：
1. 阅读当前项目状态快照。
2. 从固定动作集合中选择一个最合理的下一步动作。
3. 优先处理阻塞项和 fatal/high 风险。
4. 返回结构化 JSON。

动作集合：
- upload_tender_documents
- parse_tender_package
- generate_checklist
- upload_missing_materials
- generate_chapter_draft
- run_compliance_check
- resolve_compliance_issues
- ready_for_export

决策原则：
1. 只选一个动作。
2. 缺招标文件时先上传文件。
3. 未解析时先解析。
4. 无清单时先生成清单。
5. 缺关键材料时先补材料。
6. 无草稿时先生成章节。
7. 未做合规检查时先检查。
8. 有 fatal/high 问题时先修复，不要导出。
```

## API

### `GET /api/v1/projects/{project_id}/agent/next-action`

Returns the current best next step for the project.

## Execution Strategy

1. Build project snapshot from the database.
2. If LLM mode is enabled and configured, ask the LLM for a constrained JSON decision.
3. If LLM is unavailable or invalid, fall back to deterministic heuristics.

## Why This Works for MVP

1. The system keeps the reliable deterministic backend.
2. The user gets an AI-style project coordinator.
3. The action space stays constrained, so bad autonomous behavior is limited.
4. Later iterations can let the agent invoke tools automatically instead of only recommending them.
