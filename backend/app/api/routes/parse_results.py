from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.parse import (
    ClauseItem,
    DirectorySuggestionItem,
    EvidenceItem,
    OpenQuestionItem,
    PricingRuleItem,
    RejectionRiskItem,
    RequirementItem,
    StructureTemplateRequest,
    StructureTemplateResponse,
)
from app.services.parse_result_service import parse_result_service
from app.services.project_service import project_service


router = APIRouter()


def _ensure_project_exists(db: Session, project_id: str) -> None:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/{project_id}/directory-suggestions", response_model=list[DirectorySuggestionItem])
def list_directory_suggestions(project_id: str, db: Session = Depends(get_db)) -> list[DirectorySuggestionItem]:
    _ensure_project_exists(db, project_id)
    return parse_result_service.list_directory_suggestions(db, project_id)


@router.post("/{project_id}/structure-template/generate", response_model=StructureTemplateResponse)
def generate_structure_template(
    project_id: str,
    payload: StructureTemplateRequest,
    db: Session = Depends(get_db),
) -> StructureTemplateResponse:
    _ensure_project_exists(db, project_id)
    try:
        return parse_result_service.generate_structure_template(db, project_id, payload, regenerated=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/structure-template/regenerate", response_model=StructureTemplateResponse)
def regenerate_structure_template(
    project_id: str,
    payload: StructureTemplateRequest,
    db: Session = Depends(get_db),
) -> StructureTemplateResponse:
    _ensure_project_exists(db, project_id)
    try:
        return parse_result_service.generate_structure_template(db, project_id, payload, regenerated=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}/clauses", response_model=list[ClauseItem])
def list_clauses(project_id: str, db: Session = Depends(get_db)) -> list[ClauseItem]:
    _ensure_project_exists(db, project_id)
    return parse_result_service.list_clauses(db, project_id)


@router.get("/{project_id}/requirements", response_model=list[RequirementItem])
def list_requirements(project_id: str, db: Session = Depends(get_db)) -> list[RequirementItem]:
    _ensure_project_exists(db, project_id)
    return parse_result_service.list_requirements(db, project_id)


@router.get("/{project_id}/pricing-rules", response_model=list[PricingRuleItem])
def list_pricing_rules(project_id: str, db: Session = Depends(get_db)) -> list[PricingRuleItem]:
    _ensure_project_exists(db, project_id)
    return parse_result_service.list_pricing_rules(db, project_id)


@router.get("/{project_id}/rejection-risks", response_model=list[RejectionRiskItem])
def list_rejection_risks(project_id: str, db: Session = Depends(get_db)) -> list[RejectionRiskItem]:
    _ensure_project_exists(db, project_id)
    return parse_result_service.list_rejection_risks(db, project_id)


@router.get("/{project_id}/parse-open-questions", response_model=list[OpenQuestionItem])
def list_parse_open_questions(project_id: str, db: Session = Depends(get_db)) -> list[OpenQuestionItem]:
    _ensure_project_exists(db, project_id)
    return parse_result_service.list_open_questions(db, project_id)


@router.get("/{project_id}/evidences/{evidence_id}", response_model=EvidenceItem)
def get_evidence(project_id: str, evidence_id: str, db: Session = Depends(get_db)) -> EvidenceItem:
    _ensure_project_exists(db, project_id)
    evidence = parse_result_service.get_evidence(db, project_id, evidence_id)
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return evidence
