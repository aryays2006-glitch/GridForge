import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def registered_agent(client):
    response = client.post(
        "/api/v1/agents",
        json={"name": "GridForgeTestAgent"},
    )

    assert response.status_code in (200, 201), response.text

    data = response.json()
    assert "id" in data
    assert "api_key" in data

    return {
        "agent_id": data["id"],
        "api_key": data["api_key"],
    }


@pytest.fixture
def reviewer_headers(monkeypatch):
    reviewer_key = "test-reviewer-key-for-pytest-only"
    monkeypatch.setenv("GRIDFORGE_REVIEWER_KEY", reviewer_key)

    return {"X-Reviewer-Key": reviewer_key}


@pytest.fixture
def registered_tool(client):
    response = client.post(
        "/api/v1/tools",
        json={
            "name": "get_invoice",
            "description": "Retrieve a simulated invoice for testing.",
        },
    )

    # The tool may already exist from a previous test run.
    if response.status_code in (200, 201):
        return response.json()

    existing = client.get("/api/v1/tools")
    assert existing.status_code == 200, existing.text

    for tool in existing.json():
        if tool["name"] == "get_invoice":
            assert tool["is_active"] is True
            return tool

    pytest.fail(
        "Could not register or find the active get_invoice tool."
    )


@pytest.fixture
def registered_refund_tool(client):
    response = client.post(
        "/api/v1/tools",
        json={
            "name": "issue_refund",
            "description": "Issue a simulated refund for testing.",
        },
    )

    # The tool may already exist from a previous test run.
    if response.status_code in (200, 201):
        return response.json()

    existing = client.get("/api/v1/tools")
    assert existing.status_code == 200, existing.text

    for tool in existing.json():
        if tool["name"] == "issue_refund":
            assert tool["is_active"] is True
            return tool

    pytest.fail(
        "Could not register or find the active issue_refund tool."
    )


REFUND_ARGUMENTS = {
    "invoice_id": "INV-1002",
    "amount": 25000,
    "reason": "Duplicate charge reported by customer",
}


def agent_headers(agent):
    return {"X-API-Key": agent["api_key"]}


def validate_call(client, agent, tool_name, arguments):
    return client.post(
        "/api/v1/tool-calls/validate",
        headers=agent_headers(agent),
        json={
            "agent_id": agent["agent_id"],
            "tool_name": tool_name,
            "arguments": arguments,
        },
    )


def execute_call(
    client,
    agent,
    tool_name,
    arguments,
    approval_request_id=None,
):
    payload = {
        "agent_id": agent["agent_id"],
        "tool_name": tool_name,
        "arguments": arguments,
    }

    if approval_request_id is not None:
        payload["approval_request_id"] = approval_request_id

    return client.post(
        "/api/v1/tool-calls/execute",
        headers=agent_headers(agent),
        json=payload,
    )


def get_approvals(client, reviewer_headers, status="PENDING"):
    return client.get(
        "/api/v1/approvals",
        headers=reviewer_headers,
        params={"status": status},
    )


def review_approval(
    client,
    reviewer_headers,
    approval_id,
    decision,
    reason="Automated test review",
):
    return client.post(
        f"/api/v1/approvals/{approval_id}/review",
        headers=reviewer_headers,
        json={
            "decision": decision,
            "reason": reason,
        },
    )


def find_approval(client, reviewer_headers, request_id):
    for status in (
        "PENDING",
        "APPROVED",
        "REJECTED",
        "EXECUTING",
        "EXECUTED",
        "EXECUTION_FAILED",
    ):
        response = get_approvals(
            client,
            reviewer_headers,
            status=status,
        )
        assert response.status_code == 200, response.text

        for approval in response.json():
            if approval["request_id"] == request_id:
                return approval

    return None


# ---------------------------------------------------------
# Health and authentication
# ---------------------------------------------------------

def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()


def test_tool_call_requires_api_key(client, registered_tool):
    response = client.post(
        "/api/v1/tool-calls/validate",
        json={
            "agent_id": 1,
            "tool_name": "get_invoice",
            "arguments": {"invoice_id": "INV-1001"},
        },
    )

    assert response.status_code in (401, 403)


def test_invalid_api_key_is_rejected(
    client,
    registered_agent,
    registered_tool,
):
    response = client.post(
        "/api/v1/tool-calls/validate",
        headers={"X-API-Key": "invalid-test-api-key"},
        json={
            "agent_id": registered_agent["agent_id"],
            "tool_name": "get_invoice",
            "arguments": {"invoice_id": "INV-1001"},
        },
    )

    assert response.status_code in (401, 403)


def test_agent_cannot_use_another_agents_id(
    client,
    registered_agent,
    registered_tool,
):
    response = client.post(
        "/api/v1/tool-calls/validate",
        headers=agent_headers(registered_agent),
        json={
            "agent_id": registered_agent["agent_id"] + 100000,
            "tool_name": "get_invoice",
            "arguments": {"invoice_id": "INV-1001"},
        },
    )

    assert response.status_code in (401, 403)


# ---------------------------------------------------------
# Request validation
# ---------------------------------------------------------

def test_extra_request_fields_are_rejected(
    client,
    registered_agent,
    registered_tool,
):
    response = client.post(
        "/api/v1/tool-calls/validate",
        headers=agent_headers(registered_agent),
        json={
            "agent_id": registered_agent["agent_id"],
            "tool_name": "get_invoice",
            "arguments": {"invoice_id": "INV-1001"},
            "unexpected_field": True,
        },
    )

    assert response.status_code == 422


def test_invalid_agent_id_is_rejected(
    client,
    registered_agent,
    registered_tool,
):
    response = client.post(
        "/api/v1/tool-calls/validate",
        headers=agent_headers(registered_agent),
        json={
            "agent_id": 0,
            "tool_name": "get_invoice",
            "arguments": {"invoice_id": "INV-1001"},
        },
    )

    assert response.status_code == 422


def test_oversized_arguments_are_rejected(
    client,
    registered_agent,
    registered_tool,
):
    response = client.post(
        "/api/v1/tool-calls/validate",
        headers=agent_headers(registered_agent),
        json={
            "agent_id": registered_agent["agent_id"],
            "tool_name": "get_invoice",
            "arguments": {"large_value": "x" * 11000},
        },
    )

    assert response.status_code == 422


# ---------------------------------------------------------
# Policy validation and auditing
# ---------------------------------------------------------

def test_allowlisted_tool_returns_allow_decision(
    client,
    registered_agent,
    registered_tool,
):
    response = validate_call(
        client,
        registered_agent,
        "get_invoice",
        {"invoice_id": "INV-1001"},
    )

    assert response.status_code == 200, response.text

    data = response.json()
    assert data["decision"] == "ALLOW"
    assert data["tool_name"] == "get_invoice"
    assert 0 <= data["risk_score"] <= 100
    assert data["request_id"]


def test_unknown_tool_is_denied(
    client,
    registered_agent,
):
    response = validate_call(
        client,
        registered_agent,
        "unknown_test_tool",
        {},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Tool not found."


def test_invalid_arguments_are_denied_and_create_no_approval(
    client,
    registered_agent,
    registered_tool,
    reviewer_headers,
):
    response = validate_call(
        client,
        registered_agent,
        "get_invoice",
        {"action": "refund", "invoice_id": "INV-1001"},
    )

    assert response.status_code == 200, response.text

    data = response.json()
    assert data["decision"] == "DENY"
    assert data["request_id"]

    # A denied request must never appear in the approval queue.
    approval = find_approval(
        client,
        reviewer_headers,
        data["request_id"],
    )
    assert approval is None


def test_validation_creates_audit_record(
    client,
    registered_agent,
    registered_tool,
):
    validation = validate_call(
        client,
        registered_agent,
        "get_invoice",
        {"invoice_id": "INV-1001"},
    )

    assert validation.status_code == 200, validation.text

    audit_response = client.get("/api/v1/audit-logs")
    assert audit_response.status_code == 200, audit_response.text

    assert isinstance(audit_response.json(), list)


# ---------------------------------------------------------
# Reviewer authentication and approval workflow
# ---------------------------------------------------------

def test_approval_list_requires_reviewer_key(
    client,
    reviewer_headers,
):
    response = client.get("/api/v1/approvals")

    assert response.status_code in (401, 403)


def test_approval_list_accepts_reviewer_key(
    client,
    reviewer_headers,
):
    response = client.get(
        "/api/v1/approvals",
        headers=reviewer_headers,
    )

    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


def test_approval_review_rejects_invalid_reviewer_key(
    client,
    reviewer_headers,
):
    response = client.post(
        "/api/v1/approvals/999999/review",
        headers={"X-Reviewer-Key": "wrong-reviewer-key"},
        json={"decision": "APPROVED", "reason": "Test"},
    )

    assert response.status_code in (401, 403)


# ---------------------------------------------------------
# Execution safety
# ---------------------------------------------------------

def test_refund_execution_without_approval_is_blocked(
    client,
    registered_agent,
    registered_refund_tool,
):
    response = execute_call(
        client,
        registered_agent,
        "issue_refund",
        REFUND_ARGUMENTS,
    )

    assert response.status_code == 403
    assert "detail" in response.json()


def test_invalid_arguments_execution_is_blocked(
    client,
    registered_agent,
    registered_tool,
):
    response = execute_call(
        client,
        registered_agent,
        "get_invoice",
        {"action": "refund", "invoice_id": "INV-1001"},
    )

    assert response.status_code == 200, response.text

    data = response.json()
    assert data["decision"] == "DENY"
    assert data["status"] == "BLOCKED"
    assert data["result"] is None


def test_refund_execution_with_pending_approval_is_blocked(
    client,
    registered_agent,
    registered_refund_tool,
    reviewer_headers,
):
    validation = validate_call(
        client,
        registered_agent,
        "issue_refund",
        REFUND_ARGUMENTS,
    )

    assert validation.status_code == 200, validation.text
    assert validation.json()["decision"] == "REQUIRE_APPROVAL"

    request_id = validation.json()["request_id"]

    approval = find_approval(
        client,
        reviewer_headers,
        request_id,
    )
    assert approval is not None
    assert approval["status"] == "PENDING"

    execution = execute_call(
        client,
        registered_agent,
        "issue_refund",
        REFUND_ARGUMENTS,
        approval_request_id=request_id,
    )

    assert execution.status_code == 403
    assert "detail" in execution.json()

    # Verify the approval was not changed to an executed state.
    current_approval = find_approval(
        client,
        reviewer_headers,
        request_id,
    )
    assert current_approval is not None
    assert current_approval["status"] == "PENDING"


# ---------------------------------------------------------
# Refund approval workflow (issue_refund always needs approval)
# ---------------------------------------------------------

def test_refund_always_requires_approval(
    client,
    registered_agent,
    registered_refund_tool,
):
    response = validate_call(
        client,
        registered_agent,
        "issue_refund",
        REFUND_ARGUMENTS,
    )

    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "REQUIRE_APPROVAL"


def test_rejected_approval_cannot_execute(
    client,
    registered_agent,
    registered_refund_tool,
    reviewer_headers,
):
    validation = validate_call(
        client,
        registered_agent,
        "issue_refund",
        REFUND_ARGUMENTS,
    )

    assert validation.status_code == 200, validation.text
    assert validation.json()["decision"] == "REQUIRE_APPROVAL"
    request_id = validation.json()["request_id"]

    approval = find_approval(
        client,
        reviewer_headers,
        request_id,
    )
    assert approval is not None

    review = review_approval(
        client,
        reviewer_headers,
        approval["id"],
        "REJECTED",
        "Rejected by automated test",
    )
    assert review.status_code == 200, review.text

    execution = execute_call(
        client,
        registered_agent,
        "issue_refund",
        REFUND_ARGUMENTS,
        approval_request_id=request_id,
    )

    assert execution.status_code == 403
    assert "detail" in execution.json()

    current_approval = find_approval(
        client,
        reviewer_headers,
        request_id,
    )
    assert current_approval is not None
    assert current_approval["status"] == "REJECTED"


def test_approved_request_executes_mock_tool(
    client,
    registered_agent,
    registered_refund_tool,
    reviewer_headers,
):
    validation = validate_call(
        client,
        registered_agent,
        "issue_refund",
        REFUND_ARGUMENTS,
    )

    assert validation.status_code == 200, validation.text
    assert validation.json()["decision"] == "REQUIRE_APPROVAL"

    request_id = validation.json()["request_id"]

    approval = find_approval(
        client,
        reviewer_headers,
        request_id,
    )
    assert approval is not None
    assert approval["status"] == "PENDING"

    review = review_approval(
        client,
        reviewer_headers,
        approval["id"],
        "APPROVED",
        "Approved by automated test",
    )
    assert review.status_code == 200, review.text

    execution = execute_call(
        client,
        registered_agent,
        "issue_refund",
        REFUND_ARGUMENTS,
        approval_request_id=request_id,
    )

    assert execution.status_code == 200, execution.text

    result = execution.json()
    assert result["status"] == "EXECUTED"
    assert result["result"]["success"] is True
    assert result["result"]["data"]["invoice_id"] == "INV-1002"
    assert result["result"]["data"]["refunded_amount"] == 25000
    assert result["result"]["data"]["simulated"] is True

    current_approval = find_approval(
        client,
        reviewer_headers,
        request_id,
    )
    assert current_approval is not None
    assert current_approval["status"] == "EXECUTED"


def test_executed_approval_cannot_be_reused(
    client,
    registered_agent,
    registered_refund_tool,
    reviewer_headers,
):
    validation = validate_call(
        client,
        registered_agent,
        "issue_refund",
        REFUND_ARGUMENTS,
    )

    assert validation.status_code == 200, validation.text
    request_id = validation.json()["request_id"]

    approval = find_approval(
        client,
        reviewer_headers,
        request_id,
    )
    assert approval is not None

    review = review_approval(
        client,
        reviewer_headers,
        approval["id"],
        "APPROVED",
        "Approved by automated test",
    )
    assert review.status_code == 200, review.text

    first_execution = execute_call(
        client,
        registered_agent,
        "issue_refund",
        REFUND_ARGUMENTS,
        approval_request_id=request_id,
    )

    assert first_execution.status_code == 200, first_execution.text
    assert first_execution.json()["status"] == "EXECUTED"

    second_execution = execute_call(
        client,
        registered_agent,
        "issue_refund",
        REFUND_ARGUMENTS,
        approval_request_id=request_id,
    )

    assert second_execution.status_code == 403
    assert "detail" in second_execution.json()