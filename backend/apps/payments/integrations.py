"""
Integrations and external service stubs for the payments app.

All functions below are currently stubs returning realistic mock data
until real implementations are provided by teammates or other services.
"""

from typing import Any, Dict


def get_payment_gateway_status(transaction_id: str) -> Dict[str, Any]:
    """
    Check transaction status from payment gateway (e.g. Stripe, Razorpay).

    # TODO: Replace stub when payment gateway provider integration is added.
    """
    return {
        "transaction_id": transaction_id,
        "status": "success",
    }
