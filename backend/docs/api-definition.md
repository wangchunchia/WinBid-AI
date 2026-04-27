# WinBid-AI Backend API Definition

## Base

- Base path: `/api/v1`
- Transport: JSON over HTTP
- Auth: not implemented in scaffold

## Endpoints

### `GET /health`

Health check.

Response:

```json
{
  "status": "ok"
}
```

### `POST /projects`

Create a bid project.

Request:

```json
{
  "project_name": "黄冈安达不锈钢阀门采购项目",
  "project_code": "HB-VALVE-2026-001",
  "bidder_company_id": "company-001",
  "procurement_method": "competitive_negotiation",
  "deadline_at": "2026-05-01T09:00:00+08:00"
}
```

### `GET /projects`

List projects.

### `GET /projects/{project_id}`

Get project detail.

### `GET /projects/{project_id}/agent/next-action`

Get the project agent's recommended next action based on current workflow state.

### `GET /projects/{project_id}/agent/chat`

Get the latest persisted chat session under the project, including stored message history.

### `POST /projects/{project_id}/agent/chat`

Send a user message to the project agent. The backend stores the message, reads recent chat context
plus project state, and returns a persisted assistant reply. If `auto_execute=true`, the agent may
automatically call `solve` for messages such as "继续" or "上传好了".

Request:

```json
{
  "session_id": null,
  "user_message": "继续",
  "auto_execute": true
}
```

### `POST /projects/{project_id}/agent/plan`

Create or refresh a persisted Plan-and-Solve execution plan for the project.

Request:

```json
{
  "goal": "完成可审阅的投标文件草稿并通过基础合规检查",
  "refresh_existing": true
}
```

### `GET /projects/{project_id}/agent/plan`

Get the latest persisted project plan.

### `POST /projects/{project_id}/agent/solve-step`

Execute one step from the current project plan. If no `plan_id` or `step_code` is provided, the
backend executes the first actionable step in the latest plan.

Request:

```json
{
  "plan_id": "optional-plan-id",
  "step_code": "optional-step-code"
}
```

### `POST /projects/{project_id}/agent/solve`

Execute multiple plan steps continuously until the plan is completed, blocked by user input, or
the configured `max_steps` limit is reached.

Request:

```json
{
  "plan_id": "optional-plan-id",
  "max_steps": 5
}
```

### `POST /projects/{project_id}/tender-documents`

Register a tender package file or attachment.

Request:

```json
{
  "file_name": "采购文件正文.pdf",
  "file_type": "pdf",
  "doc_role": "tender_main",
  "storage_uri": "s3://winbid/tenders/main.pdf",
  "page_count": 86,
  "uploaded_by": "user"
}
```

### `GET /projects/{project_id}/tender-documents`

List registered tender package files under a project.

### `GET /projects/{project_id}/tender-documents/{document_id}/chunks`

List parsed document chunks for inspection and downstream debugging.

### `POST /projects/{project_id}/parse`

Trigger tender package parsing. If `document_ids` is empty, the backend will parse all registered
`tender_main` / `appendix` / `clarification` documents under the project.

Request:

```json
{
  "document_ids": ["doc-001", "doc-002"],
  "force_reparse": false
}
```

### `GET /projects/{project_id}/directory-suggestions`

List parsed bid directory suggestions.

### `POST /projects/{project_id}/structure-template/generate`

Generate a basic structure template from parsed clauses and pricing rules, and persist it into
`chapters`.

Request:

```json
{
  "template_mode": "basic",
  "include_technical_chapter": null,
  "include_appendix_chapter": false,
  "custom_instruction": null,
  "replace_existing": true
}
```

### `POST /projects/{project_id}/structure-template/regenerate`

Regenerate the structure template when the user is not satisfied with the current template. In the
current MVP, regeneration replaces existing `chapters` and clears draft sections and compliance
issues tied to the old structure.

### `GET /projects/{project_id}/clauses`

List parsed clauses for the project.

### `GET /projects/{project_id}/requirements`

List normalized requirements derived from clauses.

### `GET /projects/{project_id}/pricing-rules`

List parsed pricing rules.

### `GET /projects/{project_id}/rejection-risks`

List parsed rejection risks.

### `GET /projects/{project_id}/parse-open-questions`

List unresolved parser questions requiring manual confirmation.

### `GET /projects/{project_id}/evidences/{evidence_id}`

Get evidence detail, including source document, chunk, page number, and quoted text.

### `POST /projects/{project_id}/checklist/generate`

Generate bidder material checklist.

Request:

```json
{
  "requirement_codes": ["R-001", "R-002"],
  "include_recommended": true
}
```

### `GET /projects/{project_id}/checklist`

Get the generated checklist from persisted `material_requirements`.

### `GET /projects/{project_id}/checklist/missing`

Get missing required checklist items by comparing `material_requirements` and uploaded materials.

### `POST /projects/{project_id}/materials`

Register an uploaded material file.

Request:

```json
{
  "file_name": "营业执照.pdf",
  "material_type": "business_license",
  "storage_uri": "s3://winbid/materials/license.pdf",
  "material_requirement_id": "mr-001"
}
```

### `GET /projects/{project_id}/materials`

List materials under a project.

### `POST /projects/{project_id}/drafts/generate`

Generate a bid chapter draft. In the current MVP, the backend generates only the first matched chapter
from the requested chapter codes. If OpenAI draft generation is enabled in backend config, the
backend will rewrite rule-based draft sections into more formal text using the Responses API.

Request:

```json
{
  "chapter_codes": ["C01", "C02"],
  "regenerate_existing": false
}
```

### `GET /projects/{project_id}/drafts`

List persisted draft chapters and sections.

### `POST /projects/{project_id}/compliance/check`

Run compliance check.

Request:

```json
{
  "include_semantic_review": true,
  "rule_engine_results": [
    {
      "rule_code": "RULE-SIGN-001",
      "severity": "fatal",
      "status": "failed",
      "detail": "授权委托书要求签字盖章，但当前材料未发现签章页。"
    }
  ]
}
```

### `GET /projects/{project_id}/compliance/issues`

List persisted compliance issues from the latest hard-rule compliance check.

### `POST /projects/{project_id}/export`

Trigger bid package export.

Request:

```json
{
  "export_format": "markdown",
  "include_risk_report": true
}
```

## Suggested Next Additions

1. `POST /projects/{id}/tender-documents/presign`
2. `GET /projects/{id}/checklist`
3. `GET /projects/{id}/drafts`
4. `GET /projects/{id}/compliance/issues`
