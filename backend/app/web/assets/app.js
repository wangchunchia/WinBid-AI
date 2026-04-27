const API_PREFIX = "/api/v1";

const state = {
  projects: [],
  projectId: "",
  planId: null,
  chatSessionId: null,
  chatSession: null,
  agentDecision: null,
  latestPlan: null,
  latestMissing: null,
  latestTemplate: [],
  latestDrafts: [],
  latestIssues: [],
};

const els = {
  projectSelect: document.getElementById("projectSelect"),
  refreshProjectsBtn: document.getElementById("refreshProjectsBtn"),
  loadDashboardBtn: document.getElementById("loadDashboardBtn"),
  generatePlanBtn: document.getElementById("generatePlanBtn"),
  solvePlanBtn: document.getElementById("solvePlanBtn"),
  solveStepBtn: document.getElementById("solveStepBtn"),
  projectForm: document.getElementById("projectForm"),
  documentForm: document.getElementById("documentForm"),
  materialForm: document.getElementById("materialForm"),
  refreshMissingBtn: document.getElementById("refreshMissingBtn"),
  generateTemplateBtn: document.getElementById("generateTemplateBtn"),
  regenerateTemplateBtn: document.getElementById("regenerateTemplateBtn"),
  templateMode: document.getElementById("templateMode"),
  includeTech: document.getElementById("includeTech"),
  includeAppendix: document.getElementById("includeAppendix"),
  templateInstruction: document.getElementById("templateInstruction"),
  primaryActionBtn: document.getElementById("primaryActionBtn"),
  chatInput: document.getElementById("chatInput"),
  sendChatBtn: document.getElementById("sendChatBtn"),
  agentState: document.getElementById("agentState"),
  planState: document.getElementById("planState"),
  chatThread: document.getElementById("chatThread"),
  materialPanel: document.getElementById("materialPanel"),
  templatePanel: document.getElementById("templatePanel"),
  missingList: document.getElementById("missingList"),
  templateRationale: document.getElementById("templateRationale"),
  templateList: document.getElementById("templateList"),
  planBoard: document.getElementById("planBoard"),
  draftsList: document.getElementById("draftsList"),
  complianceSummary: document.getElementById("complianceSummary"),
  complianceList: document.getElementById("complianceList"),
  checklistSummary: document.getElementById("checklistSummary"),
  checklistList: document.getElementById("checklistList"),
  materialsList: document.getElementById("materialsList"),
  logOutput: document.getElementById("logOutput"),
};

function log(message, payload) {
  const ts = new Date().toLocaleTimeString();
  const line = [`[${ts}]`, message];
  if (payload !== undefined) {
    line.push(typeof payload === "string" ? payload : JSON.stringify(payload, null, 2));
  }
  els.logOutput.textContent = `${line.join(" ")}\n${els.logOutput.textContent}`;
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof data === "object" && data ? data.detail || JSON.stringify(data) : data;
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return data;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function tag(text, variant = "") {
  return `<span class="status-chip ${variant}">${escapeHtml(text)}</span>`;
}

function bubble(kind, title, body, extras = "") {
  return `
    <div class="bubble ${kind}">
      <div class="bubble-title">
        <strong>${escapeHtml(title)}</strong>
        <small>${kind === "agent" ? "Agent" : kind === "user" ? "你" : "系统"}</small>
      </div>
      <div>${body}</div>
      ${extras}
    </div>
  `;
}

function roleToBubble(message) {
  const role = message.role === "assistant" ? "agent" : message.role === "user" ? "user" : "system";
  const title = role === "agent" ? "Agent" : role === "user" ? "你" : "系统";
  return bubble(role, title, `<p>${escapeHtml(message.content).replaceAll("\n", "<br/>")}</p>`);
}

function ensureProject() {
  if (!state.projectId) throw new Error("请先创建或选择项目。");
}

function formToObject(form) {
  const formData = new FormData(form);
  const result = {};
  for (const [key, value] of formData.entries()) {
    if (value !== "") result[key] = value;
  }
  return result;
}

async function loadProjects() {
  const projects = await request(`${API_PREFIX}/projects`);
  state.projects = projects;
  if (!state.projectId && projects.length) {
    state.projectId = projects[0].id;
  }
  els.projectSelect.innerHTML = projects
    .map(
      (item) =>
        `<option value="${item.id}" ${item.id === state.projectId ? "selected" : ""}>${escapeHtml(item.project_name)} · ${escapeHtml(item.status)}</option>`
    )
    .join("");
}

function renderTemplate(chapters, rationale = "当前显示的是已保存模板。") {
  state.latestTemplate = chapters || [];
  els.templateRationale.textContent = rationale;
  if (!chapters || chapters.length === 0) {
    els.templateList.innerHTML = `<div class="hint-box">还没有模板。先解析招标文件，然后由 Agent 生成模板。</div>`;
    return;
  }
  els.templateList.innerHTML = chapters
    .map(
      (chapter) => `
        <div class="card">
          <h4>${escapeHtml(chapter.chapter_code)} · ${escapeHtml(chapter.title)}</h4>
          <div class="meta-row">
            ${tag(chapter.chapter_type)}
            ${chapter.mandatory_flag ? tag("mandatory") : tag("optional", "neutral")}
          </div>
        </div>
      `
    )
    .join("");
}

function renderChecklist(result) {
  if (!result) {
    els.checklistSummary.textContent = "尚未生成清单。";
    els.checklistList.innerHTML = "";
    return;
  }
  const summary = result.grouped_summary || {};
  els.checklistSummary.textContent = `mandatory ${summary.mandatory_count || 0} / conditional ${summary.conditional_count || 0} / bonus ${summary.bonus_count || 0} / risk ${summary.risk_count || 0}`;
  els.checklistList.innerHTML = (result.checklist_items || [])
    .map(
      (item) => `
        <div class="card">
          <h4>${escapeHtml(item.material_name)}</h4>
          <p>${escapeHtml(item.checklist_guidance)}</p>
          <div class="meta-row">
            ${tag(item.material_type)}
            ${item.submission_category === "risk" ? tag(item.submission_category, "warn") : tag(item.submission_category)}
            ${tag(`ID:${item.material_code}`, "neutral")}
          </div>
        </div>
      `
    )
    .join("");
}

function renderMaterials(materials) {
  els.materialsList.innerHTML = (materials || []).length
    ? materials
        .map(
          (item) => `
            <div class="card">
              <h4>${escapeHtml(item.file_name)}</h4>
              <div class="meta-row">
                ${tag(item.material_type)}
                ${tag(item.review_status, "neutral")}
              </div>
            </div>
          `
        )
        .join("")
    : `<div class="hint-box">还没有上传材料。</div>`;
}

function renderMissing(result) {
  state.latestMissing = result;
  const items = result?.missing_items || [];
  els.materialPanel.classList.toggle("hidden", items.length === 0);
  els.missingList.innerHTML = items.length
    ? items
        .map(
          (item) => `
            <div class="card">
              <h4>${escapeHtml(item.material_name)}</h4>
              <p>${escapeHtml(item.reason)}</p>
              <div class="meta-row">
                ${tag(item.material_type)}
                ${item.submission_category === "risk" ? tag(item.submission_category, "warn") : tag(item.submission_category)}
                ${tag(`ID:${item.material_code}`, "neutral")}
              </div>
            </div>
          `
        )
        .join("")
    : `<div class="hint-box">当前没有缺失材料。</div>`;
}

function renderDrafts(drafts) {
  state.latestDrafts = drafts || [];
  els.draftsList.innerHTML = drafts?.length
    ? drafts
        .map(
          (chapter) => `
            <div class="card">
              <h4>${escapeHtml(chapter.chapter_code)} · ${escapeHtml(chapter.chapter_title)}</h4>
              <div class="meta-row">
                ${tag(chapter.chapter_type)}
                ${tag(chapter.generation_status, "neutral")}
                ${tag(`sections:${chapter.chapter_summary.generated_section_count}`)}
              </div>
              <p>${escapeHtml((chapter.draft_sections?.[0]?.generated_text || "暂无内容").slice(0, 120))}</p>
            </div>
          `
        )
        .join("")
    : `<div class="hint-box">还没有章节草稿。</div>`;
}

function renderCompliance(issues) {
  state.latestIssues = issues || [];
  const fatal = issues.filter((i) => i.severity === "fatal").length;
  const high = issues.filter((i) => i.severity === "high").length;
  els.complianceSummary.textContent = issues.length
    ? `fatal ${fatal} / high ${high} / total ${issues.length}`
    : "当前没有合规问题。";
  els.complianceList.innerHTML = issues.length
    ? issues
        .map(
          (issue) => `
            <div class="card">
              <h4>${escapeHtml(issue.issue_title)}</h4>
              <p>${escapeHtml(issue.issue_detail)}</p>
              <div class="meta-row">
                ${issue.severity === "fatal" || issue.severity === "high" ? tag(issue.severity, "warn") : tag(issue.severity)}
                ${tag(issue.issue_type, "neutral")}
              </div>
            </div>
          `
        )
        .join("")
    : "";
}

function renderPlan(plan) {
  state.latestPlan = plan;
  state.planId = plan?.plan_id || null;
  els.planState.textContent = plan?.plan_status || "未生成";
  els.planBoard.innerHTML = plan?.steps?.length
    ? plan.steps
        .map(
          (step) => `
            <div class="card">
              <h4>${escapeHtml(step.step_code)} · ${escapeHtml(step.step_title)}</h4>
              <div class="meta-row">
                ${tag(step.action_name)}
                ${step.status === "blocked" ? tag(step.status, "warn") : tag(step.status, "neutral")}
              </div>
              <p>${escapeHtml(step.blocking_reason || step.result_summary || "等待 Agent 推进")}</p>
            </div>
          `
        )
        .join("")
    : `<div class="hint-box">还没有生成计划。</div>`;
}

function buildPrimaryAction() {
  const decision = state.agentDecision;
  if (!decision) {
    return { label: "刷新状态", action: loadWorkspace };
  }
  const mapping = {
    upload_tender_documents: { label: "先登记招标文件", action: focusDocumentForm },
    parse_tender_package: { label: "开始解析招标文件", action: parseProject },
    generate_checklist: { label: "生成材料清单", action: generateChecklist },
    upload_missing_materials: { label: "上传缺失材料", action: focusMaterialPanel },
    generate_chapter_draft: { label: "生成章节草稿", action: generateDrafts },
    run_compliance_check: { label: "执行合规检查", action: runCompliance },
    resolve_compliance_issues: { label: "查看并处理风险问题", action: focusCompliancePanel },
    ready_for_export: { label: "项目已可导出", action: loadWorkspace },
  };
  return mapping[decision.next_action] || { label: "让 Agent 继续推进", action: solvePlan };
}

function renderChat() {
  const messages = [];
  if (!state.projectId) {
    messages.push(
      bubble("system", "开始前", "先在右侧创建一个项目，然后登记招标入口文件。后续你可以直接通过这个对话框和 Agent 对话。")
    );
  } else if (state.chatSession?.messages?.length) {
    messages.push(...state.chatSession.messages.map(roleToBubble));
  } else {
    messages.push(
      bubble("system", "当前项目", "项目已选定。你可以直接说“继续”，我会根据状态自动推进；只有在缺材料时才需要你上传。")
    );
  }

  if (state.projectId && state.agentDecision && !state.chatSession?.messages?.length) {
    messages.push(
      bubble(
        "agent",
        "当前判断",
        `<p>${escapeHtml(state.agentDecision.current_assessment)}</p><p>${escapeHtml(state.agentDecision.reason)}</p>`
      )
    );
  }

  els.chatThread.innerHTML = messages.join("");
  const primary = buildPrimaryAction();
  els.primaryActionBtn.textContent = primary.label;
  els.primaryActionBtn.onclick = async () => {
    try {
      await primary.action();
    } catch (error) {
      notifyError(error);
    }
  };
  els.templatePanel.classList.toggle("hidden", !state.latestTemplate.length);
}

async function createProject(event) {
  event.preventDefault();
  const payload = formToObject(els.projectForm);
  const project = await request(`${API_PREFIX}/projects`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.projectId = project.id;
  log("已创建项目", project);
  els.projectForm.reset();
  await loadProjects();
  await loadWorkspace();
}

async function registerDocument(event) {
  event.preventDefault();
  ensureProject();
  const payload = formToObject(els.documentForm);
  const result = await request(`${API_PREFIX}/projects/${state.projectId}/tender-documents`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  log("已登记招标文件", result);
  els.documentForm.reset();
  await loadWorkspace();
}

async function registerMaterial(event) {
  event.preventDefault();
  ensureProject();
  const payload = formToObject(els.materialForm);
  const result = await request(`${API_PREFIX}/projects/${state.projectId}/materials`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  log("已登记材料", result);
  els.materialForm.reset();
  await solvePlan();
}

async function parseProject() {
  ensureProject();
  const result = await request(`${API_PREFIX}/projects/${state.projectId}/parse`, {
    method: "POST",
    body: JSON.stringify({ document_ids: [], force_reparse: true }),
  });
  log("解析完成", result);
  await loadWorkspace();
}

function templatePayload() {
  return {
    template_mode: els.templateMode.value,
    include_technical_chapter: els.includeTech.checked ? true : null,
    include_appendix_chapter: els.includeAppendix.checked,
    custom_instruction: els.templateInstruction.value || null,
    replace_existing: true,
  };
}

async function generateTemplate(regenerate) {
  ensureProject();
  const endpoint = regenerate ? "regenerate" : "generate";
  const result = await request(`${API_PREFIX}/projects/${state.projectId}/structure-template/${endpoint}`, {
    method: "POST",
    body: JSON.stringify(templatePayload()),
  });
  log(regenerate ? "已重做模板" : "已生成基础模板", result);
  renderTemplate(result.result.chapters, (result.result.rationale || []).join("；"));
  await generatePlan();
  renderChat();
}

async function generateChecklist() {
  ensureProject();
  const result = await request(`${API_PREFIX}/projects/${state.projectId}/checklist/generate`, {
    method: "POST",
    body: JSON.stringify({ requirement_codes: [], include_recommended: true }),
  });
  log("已生成清单", result);
  await loadWorkspace();
}

async function generateDrafts() {
  ensureProject();
  const result = await request(`${API_PREFIX}/projects/${state.projectId}/drafts/generate`, {
    method: "POST",
    body: JSON.stringify({ chapter_codes: ["C01", "C02", "C04"], regenerate_existing: false }),
  });
  log("已生成章节草稿", result);
  await loadWorkspace();
}

async function runCompliance() {
  ensureProject();
  const result = await request(`${API_PREFIX}/projects/${state.projectId}/compliance/check`, {
    method: "POST",
    body: JSON.stringify({ include_semantic_review: false, rule_engine_results: [] }),
  });
  log("已执行合规检查", result);
  await loadWorkspace();
}

async function loadAgentDecision() {
  ensureProject();
  state.agentDecision = await request(`${API_PREFIX}/projects/${state.projectId}/agent/next-action`);
  els.agentState.textContent = state.agentDecision.next_action;
}

async function loadChatSession() {
  ensureProject();
  const suffix = state.chatSessionId ? `?session_id=${encodeURIComponent(state.chatSessionId)}` : "";
  const session = await request(`${API_PREFIX}/projects/${state.projectId}/agent/chat${suffix}`);
  state.chatSession = session;
  state.chatSessionId = session.session_id;
}

async function sendChatMessage(messageText) {
  ensureProject();
  const text = (messageText || els.chatInput.value || "").trim();
  if (!text) return;
  const result = await request(`${API_PREFIX}/projects/${state.projectId}/agent/chat`, {
    method: "POST",
    body: JSON.stringify({
      session_id: state.chatSessionId,
      user_message: text,
      auto_execute: true,
    }),
  });
  state.chatSession = result.session;
  state.chatSessionId = result.session.session_id;
  state.agentDecision = result.decision;
  if (result.solve_result) {
    state.latestPlan = result.solve_result.plan;
    state.planId = result.solve_result.plan.plan_id;
  }
  els.chatInput.value = "";
  log("会话 Agent 已回复", result);
  await loadWorkspace(true);
}

async function generatePlan() {
  ensureProject();
  const result = await request(`${API_PREFIX}/projects/${state.projectId}/agent/plan`, {
    method: "POST",
    body: JSON.stringify({
      goal: "完成可审阅的投标文件草稿并通过基础合规检查",
      refresh_existing: true,
    }),
  });
  log("已刷新计划", result);
  renderPlan(result.plan);
}

async function loadPlan() {
  ensureProject();
  try {
    const plan = await request(`${API_PREFIX}/projects/${state.projectId}/agent/plan`);
    renderPlan(plan);
  } catch {
    renderPlan(null);
  }
}

async function solveStep() {
  ensureProject();
  const result = await request(`${API_PREFIX}/projects/${state.projectId}/agent/solve-step`, {
    method: "POST",
    body: JSON.stringify({ plan_id: state.planId, step_code: null }),
  });
  log("已执行一步", result);
  renderPlan(result.plan);
  await loadWorkspace();
}

async function solvePlan() {
  await sendChatMessage("继续");
}

async function loadTemplate() {
  ensureProject();
  const chapters = await request(`${API_PREFIX}/projects/${state.projectId}/directory-suggestions`);
  renderTemplate(chapters);
}

async function loadChecklist() {
  ensureProject();
  try {
    const result = await request(`${API_PREFIX}/projects/${state.projectId}/checklist`);
    renderChecklist(result);
  } catch {
    renderChecklist(null);
  }
}

async function loadMaterials() {
  ensureProject();
  const materials = await request(`${API_PREFIX}/projects/${state.projectId}/materials`);
  renderMaterials(materials);
}

async function loadMissing() {
  ensureProject();
  try {
    const result = await request(`${API_PREFIX}/projects/${state.projectId}/checklist/missing`);
    renderMissing(result);
  } catch {
    renderMissing(null);
  }
}

async function loadDrafts() {
  ensureProject();
  const drafts = await request(`${API_PREFIX}/projects/${state.projectId}/drafts`);
  renderDrafts(drafts);
}

async function loadCompliance() {
  ensureProject();
  const issues = await request(`${API_PREFIX}/projects/${state.projectId}/compliance/issues`);
  renderCompliance(issues);
}

async function loadWorkspace(skipChatReload = false) {
  if (!state.projectId) {
    renderChat();
    return;
  }
  await Promise.allSettled([
    loadAgentDecision(),
    loadPlan(),
    ...(skipChatReload ? [] : [loadChatSession()]),
    loadTemplate(),
    loadChecklist(),
    loadMaterials(),
    loadMissing(),
    loadDrafts(),
    loadCompliance(),
  ]);
  renderChat();
}

function focusDocumentForm() {
  document.querySelector("#documentForm input[name='file_name']").focus();
}

function focusMaterialPanel() {
  els.materialPanel.classList.remove("hidden");
  document.querySelector("#materialForm input[name='file_name']").focus();
}

function focusCompliancePanel() {
  document.querySelector(".insight-rail").scrollIntoView({ behavior: "smooth", block: "start" });
}

function notifyError(error) {
  log("操作失败", error.message || String(error));
  alert(error.message || String(error));
}

function wireEvents() {
  els.projectSelect.addEventListener("change", async (event) => {
    state.projectId = event.target.value;
    await loadWorkspace();
  });
  els.refreshProjectsBtn.addEventListener("click", async () => {
    await loadProjects();
    await loadWorkspace();
  });
  els.loadDashboardBtn.addEventListener("click", () => loadWorkspace().catch(notifyError));
  els.generatePlanBtn.addEventListener("click", () => generatePlan().catch(notifyError));
  els.solvePlanBtn.addEventListener("click", () => solvePlan().catch(notifyError));
  els.solveStepBtn.addEventListener("click", () => solveStep().catch(notifyError));
  els.sendChatBtn.addEventListener("click", () => sendChatMessage().catch(notifyError));
  els.chatInput.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      sendChatMessage().catch(notifyError);
    }
  });
  els.projectForm.addEventListener("submit", (event) => createProject(event).catch(notifyError));
  els.documentForm.addEventListener("submit", (event) => registerDocument(event).catch(notifyError));
  els.materialForm.addEventListener("submit", (event) => registerMaterial(event).catch(notifyError));
  els.refreshMissingBtn.addEventListener("click", () => loadMissing().catch(notifyError));
  els.generateTemplateBtn.addEventListener("click", () => generateTemplate(false).catch(notifyError));
  els.regenerateTemplateBtn.addEventListener("click", () => generateTemplate(true).catch(notifyError));
}

async function bootstrap() {
  wireEvents();
  try {
    await loadProjects();
    if (state.projectId) {
      els.projectSelect.value = state.projectId;
    }
    renderChat();
    await loadWorkspace();
  } catch (error) {
    notifyError(error);
  }
}

bootstrap();
