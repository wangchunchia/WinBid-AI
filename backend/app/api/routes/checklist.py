from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.checklist import ChecklistGenerateRequest, ChecklistResponse, ChecklistResult, MissingChecklistResponse
from app.services.checklist_service import checklist_service
from app.services.project_service import project_service


router = APIRouter()


@router.post("/{project_id}/checklist/generate", response_model=ChecklistResponse)
def generate_checklist(
    project_id: str,
    payload: ChecklistGenerateRequest,
    db: Session = Depends(get_db),
) -> ChecklistResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return checklist_service.generate_checklist(db, project_id, payload)


@router.get("/{project_id}/checklist", response_model=ChecklistResult)
def get_checklist(project_id: str, db: Session = Depends(get_db)) -> ChecklistResult:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return checklist_service.list_checklist(db, project_id)


@router.get("/{project_id}/checklist/missing", response_model=MissingChecklistResponse)
def get_missing_checklist(project_id: str, db: Session = Depends(get_db)) -> MissingChecklistResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return checklist_service.get_missing_checklist(db, project_id)
