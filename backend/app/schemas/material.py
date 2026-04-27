from datetime import datetime

from app.schemas.common import SchemaBase


class MaterialUploadRequest(SchemaBase):
    file_name: str
    material_type: str
    storage_uri: str
    material_requirement_id: str | None = None


class MaterialUploadResponse(SchemaBase):
    id: str
    project_id: str
    file_name: str
    material_type: str
    storage_uri: str
    review_status: str
    created_at: datetime


class MaterialListItem(MaterialUploadResponse):
    material_requirement_id: str | None = None
