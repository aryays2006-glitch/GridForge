
from pydantic import BaseModel, ConfigDict, Field


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class AgentRegistrationResponse(BaseModel):
    id: int
    name: str
    api_key: str
