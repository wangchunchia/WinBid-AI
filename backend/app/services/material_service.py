from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import UserMaterial
from app.schemas.material import MaterialListItem, MaterialUploadRequest, MaterialUploadResponse


class MaterialService:
    def upload_material(self, db: Session, project_id: str, payload: MaterialUploadRequest) -> MaterialUploadResponse:
        item = UserMaterial(
            id=str(uuid4()),
            project_id=project_id,
            file_name=payload.file_name,
            material_type=payload.material_type,
            storage_uri=payload.storage_uri,
            material_requirement_id=payload.material_requirement_id,
            review_status="uploaded",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return MaterialUploadResponse.model_validate(item)

    def list_materials(self, db: Session, project_id: str) -> list[MaterialListItem]:
        materials = db.scalars(
            select(UserMaterial).where(UserMaterial.project_id == project_id).order_by(UserMaterial.created_at.desc())
        ).all()
        return [MaterialListItem.model_validate(material) for material in materials]


material_service = MaterialService()
