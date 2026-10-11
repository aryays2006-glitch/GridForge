
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApprovalReviewRequest(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(default="", max_length=500)


class ApprovalRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: str
    agent_id: int
    tool_name: str
    arguments: dict
    risk_score: int
    status: str
    reviewed_by: str | None
    review_reason: str | None
    created_at: datetime
    reviewed_at: datetime | None
