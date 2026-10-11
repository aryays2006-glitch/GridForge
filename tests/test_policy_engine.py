import pytest
from pydantic import ValidationError

from app.decision_schemas import ToolCallDecision
from app.policy_engine import DecisionType, evaluate_tool_call


def test_approved_tool_with_normal_arguments_is_allowed():
    result = evaluate_tool_call(
        tool_name="get_invoice",
        arguments={"invoice_id": "INV-1001"},
    )

    assert result.decision == DecisionType.ALLOW
    assert result.risk_score == 10


def test_unapproved_tool_is_denied():
    result = evaluate_tool_call(
        tool_name="delete_database",
        arguments={},
    )

    assert result.decision == DecisionType.DENY
    assert result.risk_score == 90


def test_unexpected_argument_is_denied():
    result = evaluate_tool_call(
        tool_name="get_invoice",
        arguments={"action": "refund"},
    )

    assert result.decision == DecisionType.DENY
    assert result.risk_score == 75


def test_extra_argument_alongside_valid_one_is_denied():
    result = evaluate_tool_call(
        tool_name="get_invoice",
        arguments={"invoice_id": "INV-1001", "action": "refund"},
    )

    assert result.decision == DecisionType.DENY
    assert result.risk_score == 75


def test_missing_arguments_are_denied():
    result = evaluate_tool_call(
        tool_name="issue_refund",
        arguments={"invoice_id": "INV-1002"},
    )

    assert result.decision == DecisionType.DENY
    assert result.risk_score == 75


def test_inactive_tool_is_denied():
    result = evaluate_tool_call(
        tool_name="get_invoice",
        arguments={"invoice_id": "INV-1001"},
        is_active=False,
    )

    assert result.decision == DecisionType.DENY
    assert result.risk_score == 100


def test_refund_tool_with_valid_arguments_requires_approval():
    result = evaluate_tool_call(
        tool_name="issue_refund",
        arguments={
            "invoice_id": "INV-1002",
            "amount": 25000,
            "reason": "Duplicate charge",
        },
    )

    assert result.decision == DecisionType.REQUIRE_APPROVAL
    assert result.risk_score == 85


def test_nested_sensitive_operation_is_denied():
    result = evaluate_tool_call(
        tool_name="get_invoice",
        arguments={
            "metadata": {
                "action": "refund",
            }
        },
    )

    assert result.decision == DecisionType.DENY
    assert result.risk_score == 75


def test_sensitive_operation_inside_nested_list_is_denied():
    result = evaluate_tool_call(
        tool_name="get_invoice",
        arguments={
            "metadata": [
                {"action": "refund"}
            ]
        },
    )

    assert result.decision == DecisionType.DENY
    assert result.risk_score == 75


def test_risk_score_above_100_is_rejected():
    with pytest.raises(ValidationError):
        ToolCallDecision(
            request_id="test-request",
            decision="ALLOW",
            reason="Test decision",
            risk_score=101,
            tool_name="get_invoice",
        )


def test_negative_risk_score_is_rejected():
    with pytest.raises(ValidationError):
        ToolCallDecision(
            request_id="test-request",
            decision="DENY",
            reason="Test decision",
            risk_score=-1,
            tool_name="get_invoice",
        )