from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.draft import DraftChapterView, DraftGenerateRequest, DraftGenerateResponse
from app.services.draft_service import draft_service
from app.services.project_service import project_service


router = APIRouter()


@router.post("/{project_id}/drafts/generate", response_model=DraftGenerateResponse)
def generate_draft(
    project_id: str,
    payload: DraftGenerateRequest,
    db: Session = Depends(get_db),
) -> DraftGenerateResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    try:
        return draft_service.generate_draft(db, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{project_id}/drafts", response_model=list[DraftChapterView])
def list_drafts(project_id: str, db: Session = Depends(get_db)) -> list[DraftChapterView]:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return draft_service.list_drafts(db, project_id)
