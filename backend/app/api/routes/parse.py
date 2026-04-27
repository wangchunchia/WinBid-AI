from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.parse import ParseRequest, ParseResponse
from app.services.orchestrator_service import orchestrator_service
from app.services.project_service import project_service


router = APIRouter()


@router.post("/{project_id}/parse", response_model=ParseResponse)
def parse_tender_package(
    project_id: str,
    payload: ParseRequest,
    db: Session = Depends(get_db),
) -> ParseResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    try:
        return orchestrator_service.parse_tender_package(db, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
