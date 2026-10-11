
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DecisionType(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class ToolCallDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    decision: DecisionType
    reason: str
    risk_score: int = Field(ge=0, le=100)
    tool_name: str
