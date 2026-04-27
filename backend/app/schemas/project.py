from datetime import datetime

from pydantic import Field

from app.schemas.common import SchemaBase


class ProjectCreateRequest(SchemaBase):
    project_name: str
    project_code: str
    bidder_company_id: str | None = None
    procurement_method: str | None = None
    deadline_at: datetime | None = None


class ProjectListItem(SchemaBase):
    id: str
    project_name: str
    project_code: str
    status: str
    created_at: datetime


class ProjectDetail(ProjectListItem):
    bidder_company_id: str | None = None
    procurement_method: str | None = None
    deadline_at: datetime | None = None
    updated_at: datetime
