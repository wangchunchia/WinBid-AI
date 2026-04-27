from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import DocumentChunk, SourceDocument
from app.schemas.source_document import DocumentChunkResponse, SourceDocumentRegisterRequest, SourceDocumentResponse


class SourceDocumentService:
    def register_document(
        self,
        db: Session,
        project_id: str,
        payload: SourceDocumentRegisterRequest,
    ) -> SourceDocumentResponse:
        document = SourceDocument(
            id=str(uuid4()),
            project_id=project_id,
            file_name=payload.file_name,
            file_type=payload.file_type,
            doc_role=payload.doc_role,
            storage_uri=payload.storage_uri,
            page_count=payload.page_count,
            parse_status="pending",
            uploaded_by=payload.uploaded_by,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        return SourceDocumentResponse.model_validate(document)

    def list_documents(self, db: Session, project_id: str) -> list[SourceDocumentResponse]:
        documents = db.scalars(
            select(SourceDocument)
            .where(SourceDocument.project_id == project_id)
            .order_by(SourceDocument.created_at.desc())
        ).all()
        return [SourceDocumentResponse.model_validate(document) for document in documents]

    def get_documents_by_ids(
        self,
        db: Session,
        project_id: str,
        document_ids: list[str],
    ) -> list[SourceDocument]:
        if not document_ids:
            return []
        return db.scalars(
            select(SourceDocument).where(
                SourceDocument.project_id == project_id,
                SourceDocument.id.in_(document_ids),
            )
        ).all()

    def get_parse_candidates(self, db: Session, project_id: str) -> list[SourceDocument]:
        return db.scalars(
            select(SourceDocument).where(
                SourceDocument.project_id == project_id,
                SourceDocument.doc_role.in_(["tender_main", "appendix", "clarification"]),
            )
        ).all()

    def list_document_chunks(self, db: Session, project_id: str, document_id: str) -> list[DocumentChunkResponse]:
        chunks = db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.project_id == project_id, DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.page_no.asc(), DocumentChunk.chunk_index.asc())
        ).all()
        return [DocumentChunkResponse.model_validate(chunk) for chunk in chunks]


source_document_service = SourceDocumentService()
