from datetime import datetime

from app.schemas.common import SchemaBase


class SourceDocumentRegisterRequest(SchemaBase):
    file_name: str
    file_type: str
    doc_role: str
    storage_uri: str
    page_count: int | None = None
    uploaded_by: str = "user"


class SourceDocumentResponse(SchemaBase):
    id: str
    project_id: str
    file_name: str
    file_type: str
    doc_role: str
    storage_uri: str
    page_count: int | None = None
    parse_status: str
    uploaded_by: str
    created_at: datetime
    updated_at: datetime


class DocumentChunkResponse(SchemaBase):
    id: str
    project_id: str
    document_id: str
    page_no: int
    chunk_index: int
    chunk_type: str
    text_content: str
    char_count: int
    created_at: datetime
    updated_at: datetime
