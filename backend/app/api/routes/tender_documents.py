from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.source_document import DocumentChunkResponse, SourceDocumentRegisterRequest, SourceDocumentResponse
from app.services.project_service import project_service
from app.services.source_document_service import source_document_service


router = APIRouter()


@router.post(
    "/{project_id}/tender-documents",
    response_model=SourceDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_tender_document(
    project_id: str,
    payload: SourceDocumentRegisterRequest,
    db: Session = Depends(get_db),
) -> SourceDocumentResponse:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return source_document_service.register_document(db, project_id, payload)


@router.get("/{project_id}/tender-documents", response_model=list[SourceDocumentResponse])
def list_tender_documents(project_id: str, db: Session = Depends(get_db)) -> list[SourceDocumentResponse]:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return source_document_service.list_documents(db, project_id)


@router.get("/{project_id}/tender-documents/{document_id}/chunks", response_model=list[DocumentChunkResponse])
def list_document_chunks(
    project_id: str,
    document_id: str,
    db: Session = Depends(get_db),
) -> list[DocumentChunkResponse]:
    if not project_service.exists(db, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return source_document_service.list_document_chunks(db, project_id, document_id)
