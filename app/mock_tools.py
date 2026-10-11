import math
from typing import Any


# Fake invoice records for local testing only.
MOCK_INVOICES = {
    "INV-1001": {
        "invoice_id": "INV-1001",
        "customer": "Acme Demo Ltd.",
        "amount": 25000,
        "currency": "INR",
        "status": "PENDING",
    },
    "INV-1002": {
        "invoice_id": "INV-1002",
        "customer": "Example Industries",
        "amount": 75000,
        "currency": "INR",
        "status": "PAID",
    },
}


def get_invoice(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return a simulated invoice after validating the input."""

    # Reject unexpected arguments rather than silently ignoring them.
    unexpected_arguments = set(arguments) - {"invoice_id"}

    if unexpected_arguments:
        return {
            "success": False,
            "error": "Unexpected arguments are not allowed.",
        }

    invoice_id = arguments.get("invoice_id")

    if not isinstance(invoice_id, str) or not invoice_id.strip():
        return {
            "success": False,
            "error": "A valid invoice_id is required.",
        }

    invoice = MOCK_INVOICES.get(invoice_id.strip())

    if invoice is None:
        return {
            "success": False,
            "error": "Invoice not found in the mock database.",
        }

    # Return a copy so callers cannot modify the stored mock record.
    return {
        "success": True,
        "data": invoice.copy(),
    }


def issue_refund(arguments: dict[str, Any]) -> dict[str, Any]:
    """Simulate a refund. No money moves and no stored data changes."""

    unexpected_arguments = set(arguments) - {
        "invoice_id",
        "amount",
        "reason",
    }

    if unexpected_arguments:
        return {
            "success": False,
            "error": "Unexpected arguments are not allowed.",
        }

    invoice_id = arguments.get("invoice_id")
    amount = arguments.get("amount")
    reason = arguments.get("reason")

    if not isinstance(invoice_id, str) or not invoice_id.strip():
        return {
            "success": False,
            "error": "A valid invoice_id is required.",
        }

    # bool is a subclass of int in Python, so exclude it explicitly.
    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not math.isfinite(amount)
        or amount <= 0
    ):
        return {
            "success": False,
            "error": "amount must be a positive number.",
        }

    if not isinstance(reason, str) or not reason.strip():
        return {
            "success": False,
            "error": "A refund reason is required.",
        }

    invoice = MOCK_INVOICES.get(invoice_id.strip())

    if invoice is None:
        return {
            "success": False,
            "error": "Invoice not found in the mock database.",
        }

    if invoice["status"] != "PAID":
        return {
            "success": False,
            "error": "Only paid invoices can be refunded.",
        }

    if amount > invoice["amount"]:
        return {
            "success": False,
            "error": "Refund amount exceeds the invoice amount.",
        }

    return {
        "success": True,
        "data": {
            "invoice_id": invoice["invoice_id"],
            "refunded_amount": amount,
            "currency": invoice["currency"],
            "reason": reason.strip(),
            "simulated": True,
        },
    }


def execute_mock_tool(
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Execute only tools explicitly registered in this mock registry."""

    tool_registry = {
        "get_invoice": get_invoice,
        "issue_refund": issue_refund,
    }

    tool_function = tool_registry.get(tool_name)

    if tool_function is None:
        return {
            "success": False,
            "error": "Tool is not available for execution.",
        }

    return tool_function(arguments)