from pydantic import BaseModel, ConfigDict, Field


class SchemaBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MessageResponse(SchemaBase):
    message: str


class AgentEnvelope(SchemaBase):
    run_id: str
    agent_name: str
    project_id: str
    status: str = Field(default="success")
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
