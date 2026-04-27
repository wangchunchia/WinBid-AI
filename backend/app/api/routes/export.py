from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.export import ExportRequest, ExportResponse
from app.services.orchestrator_service import orchestrator_service
from app.services.project_service import project_service


router = APIRouter()


@router.post("/{project_id}/export", response_model=ExportResponse)
def export_bid_package(
    project_id: str,
    payload: ExportRequest,
    db: Session = Depends(get_db),
) -> ExportResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return orchestrator_service.export_bid_package(project_id, payload)
