from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import TenderProject
from app.schemas.project import ProjectCreateRequest, ProjectDetail, ProjectListItem


class ProjectService:
    def create_project(self, db: Session, payload: ProjectCreateRequest) -> ProjectDetail:
        project = TenderProject(
            id=str(uuid4()),
            project_code=payload.project_code,
            project_name=payload.project_name,
            status="created",
            bidder_company_id=payload.bidder_company_id,
            procurement_method=payload.procurement_method,
            deadline_at=payload.deadline_at,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        return ProjectDetail.model_validate(project)

    def list_projects(self, db: Session) -> list[ProjectListItem]:
        projects = db.scalars(select(TenderProject).order_by(TenderProject.created_at.desc())).all()
        return [ProjectListItem.model_validate(project) for project in projects]

    def get_project(self, db: Session, project_id: str) -> ProjectDetail | None:
        project = db.get(TenderProject, project_id)
        if not project:
            return None
        return ProjectDetail(
            id=project_id,
            project_name=project.project_name,
            project_code=project.project_code,
            status=project.status,
            bidder_company_id=project.bidder_company_id,
            procurement_method=project.procurement_method,
            deadline_at=project.deadline_at,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    def exists(self, db: Session, project_id: str) -> bool:
        return db.get(TenderProject, project_id) is not None


project_service = ProjectService()
