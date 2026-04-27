from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.material import MaterialListItem, MaterialUploadRequest, MaterialUploadResponse
from app.services.material_service import material_service
from app.services.project_service import project_service


router = APIRouter()


@router.post("/{project_id}/materials", response_model=MaterialUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_material(
    project_id: str,
    payload: MaterialUploadRequest,
    db: Session = Depends(get_db),
) -> MaterialUploadResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return material_service.upload_material(db, project_id, payload)


@router.get("/{project_id}/materials", response_model=list[MaterialListItem])
def list_materials(project_id: str, db: Session = Depends(get_db)) -> list[MaterialListItem]:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return material_service.list_materials(db, project_id)
