from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.compliance import ComplianceCheckRequest, ComplianceCheckResponse, ComplianceIssueItem
from app.services.compliance_service import compliance_service
from app.services.project_service import project_service


router = APIRouter()


@router.post("/{project_id}/compliance/check", response_model=ComplianceCheckResponse)
def run_compliance_check(
    project_id: str,
    payload: ComplianceCheckRequest,
    db: Session = Depends(get_db),
) -> ComplianceCheckResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return compliance_service.run_check(db, project_id, payload)


@router.get("/{project_id}/compliance/issues", response_model=list[ComplianceIssueItem])
def list_compliance_issues(project_id: str, db: Session = Depends(get_db)) -> list[ComplianceIssueItem]:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return compliance_service.list_issues(db, project_id)
