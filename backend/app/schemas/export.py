from pydantic import BaseModel


class ExportRequest(BaseModel):
    export_format: str = "markdown"
    include_risk_report: bool = True


class ExportResponse(BaseModel):
    project_id: str
    export_format: str
    status: str
    download_uri: str

