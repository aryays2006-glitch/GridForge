
from pydantic import BaseModel, ConfigDict, Field

from app.tool_call_schemas import ToolCallRequest


class ToolExecutionRequest(ToolCallRequest):
    model_config = ConfigDict(extra="forbid")

    approval_request_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
    )


class ToolExecutionResponse(BaseModel):
    request_id: str
    decision: str
    status: str
    reason: str
    risk_score: int = Field(ge=0, le=100)
    tool_name: str
    result: dict | None = None
