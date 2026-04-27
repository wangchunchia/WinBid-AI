import json
import re
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.domain import (
    AgentRun,
    Chapter,
    Clause,
    Evidence,
    ParseOpenQuestion,
    PricingRule,
    RejectionRisk,
    Requirement,
    TenderProject,
)
from app.schemas.checklist import (
    ChecklistGenerateRequest,
    ChecklistResponse,
    ChecklistResult,
    ChecklistSummary,
    ChecklistItem,
)
from app.schemas.parse import DocumentRef
from app.services.document_parse_service import ParsedChunkData, document_parse_service
from app.services.source_document_service import source_document_service
from app.schemas.compliance import (
    ComplianceCheckRequest,
    ComplianceCheckResponse,
    ComplianceIssueItem,
    ComplianceResult,
    CoverageReport,
    IssueSummary,
)
from app.schemas.draft import (
    ChapterSummary,
    DraftGenerateRequest,
    DraftGenerateResponse,
    DraftResult,
    DraftSectionItem,
)
from app.schemas.export import ExportRequest, ExportResponse
from app.schemas.parse import (
    ClauseItem,
    DirectorySuggestionItem,
    OpenQuestionItem,
    ParseRequest,
    ParseResponse,
    ParseResult,
    PricingRuleItem,
    ProjectSummary,
    RejectionRiskItem,
    RequirementItem,
)


class OrchestratorService:
    def __init__(self) -> None:
        self._rule_keywords = ("必须", "须", "应", "不得", "提供", "提交", "加盖", "签字", "报价", "废标", "无效")
        self._leading_number_pattern = re.compile(r"^\s*[0-9一二三四五六七八九十百千]+[、.．\)]\s*")

    def _clear_parse_results(self, db: Session, project_id: str) -> None:
        clause_ids_subquery = select(Clause.id).where(Clause.project_id == project_id)
        db.execute(delete(Requirement).where(Requirement.clause_id.in_(clause_ids_subquery)))
        db.execute(delete(Clause).where(Clause.project_id == project_id))
        db.execute(delete(Chapter).where(Chapter.project_id == project_id))
        db.execute(delete(PricingRule).where(PricingRule.project_id == project_id))
        db.execute(delete(RejectionRisk).where(RejectionRisk.project_id == project_id))
        db.execute(delete(ParseOpenQuestion).where(ParseOpenQuestion.project_id == project_id))
        db.execute(delete(Evidence).where(Evidence.project_id == project_id))

    def _persist_parse_results(self, db: Session, project_id: str, result: ParseResult) -> None:
        clause_id_by_code: dict[str, str] = {}
        evidence_id_by_ref: dict[str, str] = {}

        for evidence_ref in self._collect_evidence_refs(result):
            evidence_payload = self._evidence_payloads.get(evidence_ref)
            if not evidence_payload:
                continue
            evidence_id = str(uuid4())
            evidence_id_by_ref[evidence_ref] = evidence_id
            db.add(
                Evidence(
                    id=evidence_id,
                    project_id=project_id,
                    document_id=evidence_payload["document_id"],
                    chunk_id=evidence_payload.get("chunk_id"),
                    page_no=evidence_payload.get("page_no"),
                    quote_text=evidence_payload["quote_text"],
                    normalized_text=evidence_payload.get("normalized_text"),
                    evidence_type=evidence_payload["evidence_type"],
                    confidence_score=evidence_payload.get("confidence_score"),
                )
            )

        for index, chapter in enumerate(result.directory_suggestion, start=1):
            db.add(
                Chapter(
                    id=str(uuid4()),
                    project_id=project_id,
                    chapter_code=chapter.chapter_code,
                    title=chapter.title,
                    chapter_order=index,
                    chapter_type=chapter.chapter_type,
                    generation_status="suggested",
                )
            )

        for clause in result.clauses:
            clause_id = str(uuid4())
            clause_id_by_code[clause.clause_code] = clause_id
            db.add(
                Clause(
                    id=clause_id,
                    project_id=project_id,
                    clause_code=clause.clause_code,
                    clause_category=clause.clause_category,
                    clause_title=clause.clause_title,
                    clause_text=clause.clause_text,
                    source_evidence_id=evidence_id_by_ref.get(clause.evidence_refs[0]) if clause.evidence_refs else None,
                    importance_level=clause.importance_level,
                    risk_level=clause.risk_level,
                    needs_response=clause.needs_response,
                )
            )

        for requirement in result.requirements:
            linked_clause_id = clause_id_by_code.get(requirement.linked_clause_code)
            if not linked_clause_id:
                continue
            db.add(
                Requirement(
                    id=str(uuid4()),
                    clause_id=linked_clause_id,
                    requirement_type=requirement.requirement_type,
                    requirement_text=requirement.requirement_text,
                    response_mode=requirement.response_mode,
                    acceptance_rule=requirement.acceptance_rule,
                    source_evidence_id=evidence_id_by_ref.get(requirement.evidence_refs[0]) if requirement.evidence_refs else None,
                    mandatory_flag=requirement.mandatory_flag,
                )
            )

        for pricing_rule in result.pricing_rules:
            db.add(
                PricingRule(
                    id=str(uuid4()),
                    project_id=project_id,
                    rule_code=pricing_rule.rule_code,
                    rule_text=pricing_rule.rule_text,
                    source_evidence_id=evidence_id_by_ref.get(pricing_rule.evidence_refs[0]) if pricing_rule.evidence_refs else None,
                )
            )

        for rejection_risk in result.rejection_risks:
            db.add(
                RejectionRisk(
                    id=str(uuid4()),
                    project_id=project_id,
                    risk_code=rejection_risk.risk_code,
                    severity=rejection_risk.severity,
                    risk_text=rejection_risk.risk_text,
                    source_evidence_id=evidence_id_by_ref.get(rejection_risk.evidence_refs[0]) if rejection_risk.evidence_refs else None,
                )
            )

        for question in result.open_questions:
            db.add(
                ParseOpenQuestion(
                    id=str(uuid4()),
                    project_id=project_id,
                    question=question.question,
                    related_document_ids_json=json.dumps(question.related_document_ids, ensure_ascii=False),
                )
            )

    def _infer_clause_category(self, text: str) -> str:
        if any(keyword in text for keyword in ("废标", "无效投标", "否决")):
            return "rejection"
        if any(keyword in text for keyword in ("报价", "限价", "单价", "总价", "税")):
            return "pricing"
        if any(keyword in text for keyword in ("营业执照", "资质", "资格", "供应商", "投标人")):
            return "qualification"
        if any(keyword in text for keyword in ("盖章", "签字", "密封", "正本", "副本", "格式")):
            return "format"
        if any(keyword in text for keyword in ("截止", "开标", "时间", "日期")):
            return "deadline"
        if any(keyword in text for keyword in ("技术", "参数", "规格", "性能", "材质")):
            return "technical"
        return "commercial"

    def _infer_risk_level(self, text: str, category: str) -> str:
        if category == "rejection" or any(keyword in text for keyword in ("废标", "无效投标", "否决")):
            return "fatal"
        if any(keyword in text for keyword in ("必须", "不得", "签字", "盖章", "截止")):
            return "high"
        return "medium"

    def _infer_response_mode(self, category: str, text: str) -> str:
        if category == "pricing":
            return "quote_number"
        if any(keyword in text for keyword in ("提供", "提交", "附", "扫描件", "复印件")):
            return "attach_file"
        return "write_statement"

    def _collect_evidence_refs(self, result: ParseResult) -> set[str]:
        refs: set[str] = set()
        for chapter in result.directory_suggestion:
            refs.update(chapter.evidence_refs)
        for clause in result.clauses:
            refs.update(clause.evidence_refs)
        for requirement in result.requirements:
            refs.update(requirement.evidence_refs)
        for rule in result.pricing_rules:
            refs.update(rule.evidence_refs)
        for risk in result.rejection_risks:
            refs.update(risk.evidence_refs)
        return refs

    def _extract_candidate_sentences(self, chunks: list[ParsedChunkData]) -> list[dict[str, str | int | None]]:
        candidates: list[dict[str, str | int | None]] = []
        seen: set[str] = set()
        seen_fingerprints: set[str] = set()
        splitter = re.compile(r"(?<=[。；！？\n])")

        for chunk in chunks:
            parts = [part.strip() for part in splitter.split(chunk.text_content) if part.strip()]
            for part in parts:
                normalized = re.sub(r"\s+", " ", part)
                if len(normalized) < 12:
                    continue
                if not any(keyword in normalized for keyword in self._rule_keywords):
                    continue
                fingerprint = self._build_text_fingerprint(normalized)
                if normalized in seen:
                    continue
                if fingerprint and fingerprint in seen_fingerprints:
                    continue
                seen.add(normalized)
                if fingerprint:
                    seen_fingerprints.add(fingerprint)
                candidates.append(
                    {
                        "text": normalized,
                        "document_id": chunk.document_id,
                        "chunk_id": chunk.chunk_id,
                        "page_no": chunk.page_no,
                    }
                )

        return candidates[:60]

    def _build_text_fingerprint(self, text: str) -> str:
        normalized = self._leading_number_pattern.sub("", text)
        normalized = re.sub(r"\s+", "", normalized)
        normalized = re.sub(r"[0-9０-９]", "", normalized)
        normalized = re.sub(r"[，,。；;：:、（）()【】\\[\\]《》“”\"'‘’·/\\\\_-]", "", normalized)
        return normalized[:160]

    def _build_directory_suggestions(
        self,
        has_pricing: bool,
        has_technical: bool,
    ) -> list[DirectorySuggestionItem]:
        chapters = [
            DirectorySuggestionItem(
                chapter_code="C01",
                title="资格证明文件",
                chapter_type="qualification",
                mandatory_flag=True,
                evidence_refs=[],
            ),
            DirectorySuggestionItem(
                chapter_code="C02",
                title="商务响应文件",
                chapter_type="commercial",
                mandatory_flag=True,
                evidence_refs=[],
            ),
        ]
        if has_technical:
            chapters.append(
                DirectorySuggestionItem(
                    chapter_code="C03",
                    title="技术响应文件",
                    chapter_type="technical",
                    mandatory_flag=True,
                    evidence_refs=[],
                )
            )
        if has_pricing:
            chapters.append(
                DirectorySuggestionItem(
                    chapter_code="C04",
                    title="报价文件",
                    chapter_type="pricing",
                    mandatory_flag=True,
                    evidence_refs=[],
                )
            )
        return chapters

    def _build_parse_result(
        self,
        project_name: str,
        procurement_method: str,
        deadline_at: str | None,
        parsed_documents: list[DocumentRef],
        parsed_chunks: list[ParsedChunkData],
        warnings: list[str],
    ) -> ParseResult:
        self._evidence_payloads: dict[str, dict[str, str | int | float | None]] = {}
        candidates = self._extract_candidate_sentences(parsed_chunks)
        clauses: list[ClauseItem] = []
        requirements: list[RequirementItem] = []
        pricing_rules: list[PricingRuleItem] = []
        rejection_risks: list[RejectionRiskItem] = []
        seen_clause_fingerprints: set[str] = set()
        seen_pricing_fingerprints: set[str] = set()
        seen_risk_fingerprints: set[str] = set()

        has_pricing = False
        has_technical = False

        for index, candidate in enumerate(candidates, start=1):
            sentence = str(candidate["text"])
            sentence_fingerprint = self._build_text_fingerprint(sentence)
            if sentence_fingerprint and sentence_fingerprint in seen_clause_fingerprints:
                continue
            if sentence_fingerprint:
                seen_clause_fingerprints.add(sentence_fingerprint)
            evidence_ref = f"EV-{index:03d}"
            self._evidence_payloads[evidence_ref] = {
                "document_id": str(candidate["document_id"]),
                "chunk_id": str(candidate["chunk_id"]) if candidate.get("chunk_id") else None,
                "page_no": int(candidate["page_no"]) if candidate.get("page_no") is not None else None,
                "quote_text": sentence,
                "normalized_text": sentence,
                "evidence_type": "clause",
                "confidence_score": 0.75,
            }

            category = self._infer_clause_category(sentence)
            if category == "pricing":
                has_pricing = True
            if category == "technical":
                has_technical = True

            clause_code = f"Q-{index:03d}"
            risk_level = self._infer_risk_level(sentence, category)
            clause = ClauseItem(
                clause_code=clause_code,
                clause_category=category,
                clause_title=sentence[:40],
                clause_text=sentence,
                importance_level="mandatory" if any(keyword in sentence for keyword in ("必须", "须", "不得", "应")) else "info",
                risk_level=risk_level,
                needs_response=category != "deadline",
                evidence_refs=[evidence_ref],
            )
            clauses.append(clause)

            if clause.needs_response:
                requirements.append(
                    RequirementItem(
                        requirement_code=f"R-{index:03d}",
                        linked_clause_code=clause_code,
                        requirement_type="pricing" if category == "pricing" else "content",
                        requirement_text=sentence,
                        response_mode=self._infer_response_mode(category, sentence),
                        acceptance_rule="需要人工复核具体满足方式",
                        mandatory_flag=clause.importance_level == "mandatory",
                        evidence_refs=[evidence_ref],
                    )
                )

            if category == "pricing":
                if sentence_fingerprint not in seen_pricing_fingerprints:
                    seen_pricing_fingerprints.add(sentence_fingerprint)
                    pricing_rules.append(
                        PricingRuleItem(
                            rule_code=f"P-{len(pricing_rules) + 1:03d}",
                            rule_text=sentence,
                            evidence_refs=[evidence_ref],
                        )
                    )

            if category == "rejection":
                if sentence_fingerprint not in seen_risk_fingerprints:
                    seen_risk_fingerprints.add(sentence_fingerprint)
                    rejection_risks.append(
                        RejectionRiskItem(
                            risk_code=f"X-{len(rejection_risks) + 1:03d}",
                            severity="fatal",
                            risk_text=sentence,
                            evidence_refs=[evidence_ref],
                        )
                    )

        if not clauses and parsed_chunks:
            preview = parsed_chunks[0].text_content[:120]
            evidence_ref = "EV-001"
            self._evidence_payloads[evidence_ref] = {
                "document_id": parsed_chunks[0].document_id,
                "chunk_id": parsed_chunks[0].chunk_id,
                "page_no": parsed_chunks[0].page_no,
                "quote_text": preview,
                "normalized_text": preview,
                "evidence_type": "clause",
                "confidence_score": 0.3,
            }
            clauses.append(
                ClauseItem(
                    clause_code="Q-001",
                    clause_category="commercial",
                    clause_title="文档内容预览",
                    clause_text=preview,
                    importance_level="info",
                    risk_level="low",
                    needs_response=False,
                    evidence_refs=[evidence_ref],
                )
            )

        open_questions = [
            OpenQuestionItem(
                question=warning,
                related_document_ids=[doc.document_id for doc in parsed_documents],
            )
            for warning in warnings
        ]

        if not open_questions:
            open_questions.append(
                OpenQuestionItem(
                    question="已完成基础解析，建议人工复核条款分类与 OCR 结果。",
                    related_document_ids=[doc.document_id for doc in parsed_documents],
                )
            )

        return ParseResult(
            parsed_documents=parsed_documents,
            project_summary=ProjectSummary(
                project_name=project_name,
                procurement_method=procurement_method,
                deadline_at=deadline_at,
                bid_submission_method="unknown",
            ),
            directory_suggestion=self._build_directory_suggestions(has_pricing=has_pricing, has_technical=has_technical),
            clauses=clauses,
            requirements=requirements,
            pricing_rules=pricing_rules,
            rejection_risks=rejection_risks,
            open_questions=open_questions,
        )

    def parse_tender_package(self, db: Session, project_id: str, payload: ParseRequest) -> ParseResponse:
        if payload.document_ids:
            documents = source_document_service.get_documents_by_ids(db, project_id, payload.document_ids)
            found_ids = {document.id for document in documents}
            missing_ids = [document_id for document_id in payload.document_ids if document_id not in found_ids]
        else:
            documents = source_document_service.get_parse_candidates(db, project_id)
            missing_ids = []

        if not documents:
            raise ValueError("No source documents available for parsing")

        warnings: list[str] = []
        if missing_ids:
            warnings.append(f"Some requested documents were not found under this project: {', '.join(missing_ids)}")

        for document in documents:
            if payload.force_reparse or document.parse_status in {"pending", "failed", "parsed"}:
                document.parse_status = "processing"

        project = db.get(TenderProject, project_id)
        if project:
            project.status = "parsing"

        parsed_document_payloads, parse_warnings = document_parse_service.parse_and_store_documents(db, project_id, documents)
        warnings.extend(parse_warnings)
        if not parsed_document_payloads:
            raise ValueError("No documents could be parsed successfully")

        run_id = str(uuid4())
        parsed_documents = [
            DocumentRef(document_id=document.id, file_name=document.file_name, doc_role=document.doc_role)
            for document in documents
            if document.parse_status == "parsed"
        ]
        parsed_chunks = [chunk for parsed_document in parsed_document_payloads for chunk in parsed_document.chunks]

        project_name = project.project_name if project else "Pending parsed project name"
        procurement_method = project.procurement_method if project and project.procurement_method else "unknown"
        deadline_at = project.deadline_at.isoformat() if project and project.deadline_at else None

        response = ParseResponse(
            run_id=run_id,
            agent_name="tender_parsing_agent",
            project_id=project_id,
            status="success",
            warnings=warnings,
            errors=[],
            result=self._build_parse_result(
                project_name=project_name,
                procurement_method=procurement_method,
                deadline_at=deadline_at,
                parsed_documents=parsed_documents,
                parsed_chunks=parsed_chunks,
                warnings=warnings,
            ),
        )

        self._clear_parse_results(db, project_id)
        self._persist_parse_results(db, project_id, response.result)

        if project:
            project.status = "parsed"

        agent_run = AgentRun(
            id=run_id,
            project_id=project_id,
            agent_name="tender_parsing_agent",
            input_json=json.dumps(payload.model_dump(), ensure_ascii=False),
            output_json=response.model_dump_json(),
            model_name="stub-orchestrator",
            run_status="success",
            latency_ms=0,
        )
        db.add(agent_run)
        db.commit()
        return response

    def generate_checklist(self, project_id: str, payload: ChecklistGenerateRequest) -> ChecklistResponse:
        item = ChecklistItem(
            material_code="M-001",
            material_type="business_license",
            material_name="营业执照复印件",
            submission_category="mandatory",
            condition_expression=None,
            preferred_format="pdf",
            checklist_guidance="上传有效营业执照扫描件，需清晰显示统一社会信用代码。",
            linked_requirement_codes=payload.requirement_codes or ["R-001"],
            evidence_refs=[],
        )
        return ChecklistResponse(
            run_id=str(uuid4()),
            agent_name="material_mapping_agent",
            project_id=project_id,
            status="success",
            warnings=[],
            errors=[],
            result=ChecklistResult(
                checklist_items=[item],
                grouped_summary=ChecklistSummary(
                    mandatory_count=1,
                    conditional_count=0,
                    bonus_count=0,
                    risk_count=0,
                ),
                missing_enterprise_capabilities=[],
            ),
        )

    def generate_draft(self, project_id: str, payload: DraftGenerateRequest) -> DraftGenerateResponse:
        chapter_code = payload.chapter_codes[0] if payload.chapter_codes else "C01"
        section = DraftSectionItem(
            section_title="章节草稿示例",
            section_order=1,
            generated_text="该内容为后端骨架占位文本，后续由标书生成 Agent 按章节生成。",
            linked_requirement_codes=["R-001"],
            linked_material_ids=[],
            evidence_refs=[],
            missing_info=["尚未接入企业材料和检索链路。"],
        )
        return DraftGenerateResponse(
            run_id=str(uuid4()),
            agent_name="bid_generation_agent",
            project_id=project_id,
            status="success",
            warnings=[],
            errors=[],
            result=DraftResult(
                chapter_code=chapter_code,
                draft_sections=[section],
                chapter_summary=ChapterSummary(generated_section_count=1, pending_section_count=1),
            ),
        )

    def run_compliance_check(self, project_id: str, payload: ComplianceCheckRequest) -> ComplianceCheckResponse:
        issues = []
        if payload.rule_engine_results:
            issues.append(
                ComplianceIssueItem(
                    issue_code="CI-001",
                    issue_type="rule_engine_failure",
                    severity=payload.rule_engine_results[0].severity,
                    issue_title="规则引擎发现待处理问题",
                    issue_detail=payload.rule_engine_results[0].detail,
                    linked_clause_codes=[],
                    linked_material_ids=[],
                    linked_chapter_codes=[],
                    evidence_refs=[],
                    resolution_suggestion="根据规则结果补充材料或修复章节后重新校验。",
                )
            )
        return ComplianceCheckResponse(
            run_id=str(uuid4()),
            agent_name="compliance_check_agent",
            project_id=project_id,
            status="success",
            warnings=[] if payload.include_semantic_review else ["Semantic review disabled for this run."],
            errors=[],
            result=ComplianceResult(
                overall_status="high_risk" if issues else "pending_review",
                issue_summary=IssueSummary(
                    fatal=sum(1 for issue in issues if issue.severity == "fatal"),
                    high=sum(1 for issue in issues if issue.severity == "high"),
                    medium=sum(1 for issue in issues if issue.severity == "medium"),
                    low=sum(1 for issue in issues if issue.severity == "low"),
                ),
                issues=issues,
                coverage_report=CoverageReport(
                    total_requirements=0,
                    covered_requirements=0,
                    uncovered_requirements=0,
                ),
            ),
        )

    def export_bid_package(self, project_id: str, payload: ExportRequest) -> ExportResponse:
        return ExportResponse(
            project_id=project_id,
            export_format=payload.export_format,
            status="queued",
            download_uri=f"/exports/{project_id}.{payload.export_format}",
        )


orchestrator_service = OrchestratorService()
