import os
import secrets
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import models, tool_models
from app.database import Base, SessionLocal, engine
from app.schemas import AgentCreate, AgentRegistrationResponse
from app.tool_schemas import ToolCreate, ToolResponse
from app.tool_call_schemas import ToolCallRequest
from app.decision_schemas import DecisionType, ToolCallDecision
from app.execution_schemas import (
    ToolExecutionRequest,
    ToolExecutionResponse,
)
from app.approval_schemas import (
    ApprovalReviewRequest,
    ApprovalRequestResponse,
)
from app.policy_engine import (
    DecisionType as PolicyDecisionType,
    PolicyDecision,
    evaluate_tool_call,
)
from app.mock_tools import execute_mock_tool


Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="GridForge",
    description="AI Agent Governance & Runtime Security Platform",
    version="0.1.0",
)


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: str
    agent_id: int
    tool_name: str
    decision: str
    reason: str
    risk_score: int
    created_at: datetime


class PermissionGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1, max_length=100)


class PermissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: int
    tool_name: str
    granted_at: datetime


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_reviewer_key(
    x_reviewer_key: str | None = Header(
        default=None,
        alias="X-Reviewer-Key",
    ),
) -> None:
    configured_key = os.getenv("GRIDFORGE_REVIEWER_KEY")

    if not configured_key:
        raise HTTPException(
            status_code=503,
            detail="Reviewer access is not configured. Set GRIDFORGE_REVIEWER_KEY.",
        )

    if not x_reviewer_key or not secrets.compare_digest(
        configured_key,
        x_reviewer_key,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing reviewer key.",
        )


def authenticate_agent(
    agent_id: int,
    api_key: str | None,
    db: Session,
):
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key.",
        )

    agent = (
        db.query(models.Agent)
        .filter(models.Agent.id == agent_id)
        .first()
    )

    if not agent or not secrets.compare_digest(agent.api_key, api_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key for this agent.",
        )

    return agent


def record_audit(
    db: Session,
    request_id: str,
    agent_id: int,
    tool_name: str,
    decision: str,
    reason: str,
    risk_score: int,
    arguments: dict,
) -> None:
    db.add(
        tool_models.AuditLog(
            request_id=request_id,
            agent_id=agent_id,
            tool_name=tool_name,
            decision=decision,
            reason=reason,
            risk_score=risk_score,
            arguments=arguments,
        )
    )


def evaluate_for_agent(
    db: Session,
    agent_id: int,
    tool: tool_models.Tool,
    arguments: dict,
) -> PolicyDecision:
    """Run the normal policy checks, then check this agent's permission."""

    policy_result = evaluate_tool_call(
        tool_name=tool.name,
        arguments=arguments,
        is_active=tool.is_active,
    )

    # Inactive tools, bad arguments and so on are already denied.
    if policy_result.decision == PolicyDecisionType.DENY:
        return policy_result

    permission = (
        db.query(tool_models.AgentToolPermission)
        .filter(
            tool_models.AgentToolPermission.agent_id == agent_id,
            tool_models.AgentToolPermission.tool_name == tool.name,
        )
        .first()
    )

    if permission is None:
        return PolicyDecision(
            decision=PolicyDecisionType.DENY,
            reason="This agent has not been granted permission to use this tool.",
            risk_score=95,
        )

    return policy_result


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "GridForge",
        "version": "0.1.0",
    }


@app.post(
    "/api/v1/agents",
    response_model=AgentRegistrationResponse,
    status_code=201,
)
def register_agent(
    agent: AgentCreate,
    db: Session = Depends(get_db),
):
    name = agent.name.strip()

    if not name:
        raise HTTPException(
            status_code=422,
            detail="Agent name cannot be empty.",
        )

    agent_record = models.Agent(
        name=name,
        api_key=secrets.token_urlsafe(32),
    )

    db.add(agent_record)
    db.commit()
    db.refresh(agent_record)

    return AgentRegistrationResponse(
        id=agent_record.id,
        name=agent_record.name,
        api_key=agent_record.api_key,
    )


@app.post(
    "/api/v1/tools",
    response_model=ToolResponse,
    status_code=201,
)
def register_tool(
    tool: ToolCreate,
    db: Session = Depends(get_db),
):
    name = tool.name.strip()

    if not name:
        raise HTTPException(
            status_code=422,
            detail="Tool name cannot be empty.",
        )

    existing_tool = (
        db.query(tool_models.Tool)
        .filter(tool_models.Tool.name == name)
        .first()
    )

    if existing_tool:
        raise HTTPException(
            status_code=409,
            detail="A tool with this name already exists.",
        )

    tool_record = tool_models.Tool(
        name=name,
        description=tool.description.strip(),
        is_active=True,
    )

    db.add(tool_record)
    db.commit()
    db.refresh(tool_record)

    return tool_record


@app.get(
    "/api/v1/tools",
    response_model=list[ToolResponse],
)
def list_tools(db: Session = Depends(get_db)):
    return (
        db.query(tool_models.Tool)
        .order_by(tool_models.Tool.id)
        .all()
    )


@app.post(
    "/api/v1/agents/{agent_id}/permissions",
    response_model=PermissionResponse,
    status_code=201,
    dependencies=[Depends(verify_reviewer_key)],
)
def grant_tool_permission(
    agent_id: int,
    grant: PermissionGrantRequest,
    db: Session = Depends(get_db),
):
    agent = (
        db.query(models.Agent)
        .filter(models.Agent.id == agent_id)
        .first()
    )

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")

    tool_name = grant.tool_name.strip()

    tool = (
        db.query(tool_models.Tool)
        .filter(tool_models.Tool.name == tool_name)
        .first()
    )

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found.")

    existing = (
        db.query(tool_models.AgentToolPermission)
        .filter(
            tool_models.AgentToolPermission.agent_id == agent.id,
            tool_models.AgentToolPermission.tool_name == tool.name,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="This agent already has permission for this tool.",
        )

    permission = tool_models.AgentToolPermission(
        agent_id=agent.id,
        tool_name=tool.name,
    )

    try:
        db.add(permission)
        db.commit()
        db.refresh(permission)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="The permission could not be saved.",
        )

    return permission


@app.get(
    "/api/v1/agents/{agent_id}/permissions",
    response_model=list[PermissionResponse],
    dependencies=[Depends(verify_reviewer_key)],
)
def list_tool_permissions(
    agent_id: int,
    db: Session = Depends(get_db),
):
    agent = (
        db.query(models.Agent)
        .filter(models.Agent.id == agent_id)
        .first()
    )

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")

    return (
        db.query(tool_models.AgentToolPermission)
        .filter(tool_models.AgentToolPermission.agent_id == agent.id)
        .order_by(tool_models.AgentToolPermission.id)
        .all()
    )


@app.post(
    "/api/v1/tool-calls/validate",
    response_model=ToolCallDecision,
)
def validate_tool_call(
    request: ToolCallRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    agent = authenticate_agent(request.agent_id, x_api_key, db)

    tool = (
        db.query(tool_models.Tool)
        .filter(tool_models.Tool.name == request.tool_name)
        .first()
    )

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found.")

    policy_result = evaluate_for_agent(
        db=db,
        agent_id=agent.id,
        tool=tool,
        arguments=request.arguments,
    )

    request_id = secrets.token_hex(16)
    decision = DecisionType(policy_result.decision.value)

    try:
        record_audit(
            db=db,
            request_id=request_id,
            agent_id=agent.id,
            tool_name=tool.name,
            decision=decision.value,
            reason=policy_result.reason,
            risk_score=policy_result.risk_score,
            arguments=request.arguments,
        )

        if decision == DecisionType.REQUIRE_APPROVAL:
            db.add(
                tool_models.ApprovalRequest(
                    request_id=request_id,
                    agent_id=agent.id,
                    tool_name=tool.name,
                    arguments=request.arguments,
                    risk_score=policy_result.risk_score,
                    status="PENDING",
                )
            )

        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="The security decision could not be recorded.",
        )

    return ToolCallDecision(
        request_id=request_id,
        decision=decision,
        reason=policy_result.reason,
        risk_score=policy_result.risk_score,
        tool_name=tool.name,
    )


@app.post(
    "/api/v1/tool-calls/execute",
    response_model=ToolExecutionResponse,
)
def execute_tool_call(
    request: ToolExecutionRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    agent = authenticate_agent(request.agent_id, x_api_key, db)

    tool = (
        db.query(tool_models.Tool)
        .filter(tool_models.Tool.name == request.tool_name)
        .first()
    )

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found.")

    policy_result = evaluate_for_agent(
        db=db,
        agent_id=agent.id,
        tool=tool,
        arguments=request.arguments,
    )

    decision = policy_result.decision.value

    # A denied request never reaches a mock tool.
    if decision == "DENY":
        request_id = secrets.token_hex(16)
        try:
            record_audit(
                db, request_id, agent.id, tool.name,
                decision, policy_result.reason,
                policy_result.risk_score, request.arguments,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail="The security decision could not be recorded.",
            )

        return ToolExecutionResponse(
            request_id=request_id,
            decision="DENY",
            status="BLOCKED",
            reason=policy_result.reason,
            risk_score=policy_result.risk_score,
            tool_name=tool.name,
            result=None,
        )

    approval = None

    # Sensitive calls require a matching approval.
    if decision == "REQUIRE_APPROVAL":
        if not request.approval_request_id:
            raise HTTPException(
                status_code=403,
                detail="Approval is required before execution.",
            )

        approval = (
            db.query(tool_models.ApprovalRequest)
            .filter(
                tool_models.ApprovalRequest.request_id
                == request.approval_request_id
            )
            .with_for_update()
            .first()
        )

        if not approval:
            raise HTTPException(
                status_code=404,
                detail="Matching approval request not found.",
            )

        if (
            approval.agent_id != agent.id
            or approval.tool_name != tool.name
            or approval.arguments != request.arguments
        ):
            raise HTTPException(
                status_code=403,
                detail="Approval does not match this agent, tool, and arguments.",
            )

        if approval.status != "APPROVED":
            raise HTTPException(
                status_code=403,
                detail=f"Request is not approved. Current status: {approval.status}.",
            )

        # Reserve the approval before running the tool.
        # A failed or interrupted execution must not permit silent reuse.
        approval.status = "EXECUTING"
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail="Approval could not be reserved for execution.",
            )

    request_id = secrets.token_hex(16)

    try:
        result = execute_mock_tool(tool.name, request.arguments)

        record_audit(
            db=db,
            request_id=request_id,
            agent_id=agent.id,
            tool_name=tool.name,
            decision="ALLOW" if approval is None else "APPROVED",
            reason=(
                policy_result.reason
                if approval is None
                else "Matching approval verified; mock tool executed."
            ),
            risk_score=policy_result.risk_score,
            arguments=request.arguments,
        )

        if approval is not None:
            approval.status = "EXECUTED"
            approval.review_reason = (
                (approval.review_reason or "")
                + " | Execution attempted."
            ).strip(" |")

        db.commit()

    except Exception:
        db.rollback()

        if approval is not None:
            # Fail closed: do not automatically make a reserved approval reusable.
            try:
                failed_approval = (
                    db.query(tool_models.ApprovalRequest)
                    .filter(
                        tool_models.ApprovalRequest.request_id
                        == request.approval_request_id
                    )
                    .first()
                )
                if failed_approval and failed_approval.status == "EXECUTING":
                    failed_approval.status = "EXECUTION_FAILED"
                    db.commit()
            except Exception:
                db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Tool execution or audit recording failed.",
        )

    return ToolExecutionResponse(
        request_id=request_id,
        decision="ALLOW" if approval is None else "APPROVED",
        status="EXECUTED" if result.get("success") else "FAILED",
        reason=(
            policy_result.reason
            if approval is None
            else "Matching approval verified; mock tool execution attempted."
        ),
        risk_score=policy_result.risk_score,
        tool_name=tool.name,
        result=result,
    )


@app.get(
    "/api/v1/approvals",
    response_model=list[ApprovalRequestResponse],
    dependencies=[Depends(verify_reviewer_key)],
)
def list_approvals(
    status: str = Query(
        default="PENDING",
        pattern="^(PENDING|APPROVED|REJECTED|EXECUTING|EXECUTED|EXECUTION_FAILED)$",
    ),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return (
        db.query(tool_models.ApprovalRequest)
        .filter(tool_models.ApprovalRequest.status == status)
        .order_by(tool_models.ApprovalRequest.id.desc())
        .limit(limit)
        .all()
    )


@app.post(
    "/api/v1/approvals/{approval_id}/review",
    response_model=ApprovalRequestResponse,
    dependencies=[Depends(verify_reviewer_key)],
)
def review_approval(
    approval_id: int,
    review: ApprovalReviewRequest,
    db: Session = Depends(get_db),
):
    approval = (
        db.query(tool_models.ApprovalRequest)
        .filter(tool_models.ApprovalRequest.id == approval_id)
        .first()
    )

    if not approval:
        raise HTTPException(
            status_code=404,
            detail="Approval request not found.",
        )

    if approval.status != "PENDING":
        raise HTTPException(
            status_code=409,
            detail=f"This request has already been reviewed: {approval.status}.",
        )

    approval.status = review.decision
    approval.reviewed_by = "local-reviewer"
    approval.review_reason = review.reason.strip() or None
    approval.reviewed_at = datetime.now(timezone.utc)

    try:
        db.commit()
        db.refresh(approval)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="The approval decision could not be saved.",
        )

    return approval


@app.get(
    "/api/v1/audit-logs",
    response_model=list[AuditLogResponse],
)
def list_audit_logs(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return (
        db.query(tool_models.AuditLog)
        .order_by(tool_models.AuditLog.id.desc())
        .limit(limit)
        .all()
    )