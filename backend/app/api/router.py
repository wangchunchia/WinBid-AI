from fastapi import APIRouter

from app.api.routes import (
    bid_agent,
    checklist,
    compliance,
    drafts,
    export,
    health,
    materials,
    parse,
    parse_results,
    projects,
    tender_documents,
)


api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(bid_agent.router, prefix="/projects", tags=["bid-agent"])
api_router.include_router(tender_documents.router, prefix="/projects", tags=["tender-documents"])
api_router.include_router(parse.router, prefix="/projects", tags=["parsing"])
api_router.include_router(parse_results.router, prefix="/projects", tags=["parse-results"])
api_router.include_router(checklist.router, prefix="/projects", tags=["checklist"])
api_router.include_router(materials.router, prefix="/projects", tags=["materials"])
api_router.include_router(drafts.router, prefix="/projects", tags=["drafts"])
api_router.include_router(compliance.router, prefix="/projects", tags=["compliance"])
api_router.include_router(export.router, prefix="/projects", tags=["export"])
