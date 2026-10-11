from dataclasses import dataclass
from enum import Enum
from typing import Any


class DecisionType(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


@dataclass(frozen=True)
class PolicyDecision:
    decision: DecisionType
    reason: str
    risk_score: int


# Tools GridForge is willing to evaluate at all.
ALLOWED_TOOLS = {
    "get_invoice",
    "issue_refund",
}

# Tools that change state or move money. These need a human
# decision every time, regardless of what their arguments contain.
ALWAYS_REQUIRE_APPROVAL_TOOLS = {
    "issue_refund",
}

SENSITIVE_ARGUMENT_NAMES = {
    "action",
    "operation",
    "command",
}

SENSITIVE_ACTIONS = {
    "delete",
    "transfer",
    "payment",
    "refund",
    "send_email",
}


def contains_sensitive_operation(value: Any) -> bool:
    """Recursively inspect argument data for sensitive operations."""

    if isinstance(value, dict):
        for key, nested_value in value.items():
            normalized_key = str(key).strip().lower()

            if normalized_key in SENSITIVE_ARGUMENT_NAMES:
                normalized_value = str(nested_value).strip().lower()

                if normalized_value in SENSITIVE_ACTIONS:
                    return True

            if contains_sensitive_operation(nested_value):
                return True

        return False

    if isinstance(value, list):
        return any(
            contains_sensitive_operation(item)
            for item in value
        )

    if isinstance(value, str):
        return value.strip().lower() in SENSITIVE_ACTIONS

    return False


def evaluate_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    is_active: bool = True,
) -> PolicyDecision:
    """Evaluate a tool call without executing it."""

    if not is_active:
        return PolicyDecision(
            decision=DecisionType.DENY,
            reason="The requested tool is inactive.",
            risk_score=100,
        )

    if tool_name not in ALLOWED_TOOLS:
        return PolicyDecision(
            decision=DecisionType.DENY,
            reason="The requested tool is not on the allowlist.",
            risk_score=90,
        )

    if tool_name in ALWAYS_REQUIRE_APPROVAL_TOOLS:
        return PolicyDecision(
            decision=DecisionType.REQUIRE_APPROVAL,
            reason=(
                "This tool changes financial data and always "
                "requires human approval."
            ),
            risk_score=85,
        )

    if contains_sensitive_operation(arguments):
        return PolicyDecision(
            decision=DecisionType.REQUIRE_APPROVAL,
            reason="The request contains a sensitive operation.",
            risk_score=80,
        )

    return PolicyDecision(
        decision=DecisionType.ALLOW,
        reason=(
            "The tool is allowlisted and no recognized "
            "sensitive operation was detected."
        ),
        risk_score=10,
    )