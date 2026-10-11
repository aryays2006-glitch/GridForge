
from sqlalchemy import Boolean, Column, Integer, String, DateTime, JSON
from sqlalchemy.sql import func

from app.database import Base


class Tool(Base):
    __tablename__ = "tools"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    description = Column(String, nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    request_id = Column(String, nullable=False, index=True)
    agent_id = Column(Integer, nullable=False, index=True)
    tool_name = Column(String, nullable=False, index=True)

    decision = Column(String, nullable=False)
    reason = Column(String, nullable=False)
    risk_score = Column(Integer, nullable=False)

    arguments = Column(JSON, nullable=False, default=dict)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(Integer, primary_key=True, index=True)

    request_id = Column(String, nullable=False, unique=True, index=True)
    agent_id = Column(Integer, nullable=False, index=True)
    tool_name = Column(String, nullable=False, index=True)

    arguments = Column(JSON, nullable=False, default=dict)
    risk_score = Column(Integer, nullable=False)

    status = Column(
        String,
        nullable=False,
        default="PENDING",
        index=True,
    )

    reviewed_by = Column(String, nullable=True)
    review_reason = Column(String, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    reviewed_at = Column(DateTime(timezone=True), nullable=True)
