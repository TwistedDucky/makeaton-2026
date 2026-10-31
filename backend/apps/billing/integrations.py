"""
Integrations and external service stubs for the billing app.

These functions act as anti-corruption layers and interface contracts for
functionality owned by other members (Subscriptions, Catalog, Sales).

All functions below are currently typed stubs returning realistic mock data
until real implementations are provided by teammates.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional


from apps.subscriptions.services import (
    advance_next_billing_date,
    get_due_subscriptions,
)


def calculate_tax(line: Dict[str, Any]) -> Decimal:
    """
    Calculate tax amount for an invoice line item.
    Tax is calculated on the discounted amount (line_subtotal - discount_amount).

    # TODO: Replace stub when service is available.
    Interface owned by Member 2 (catalog, plans, tax rules, discount rules).

    Expected Input Structure:
    {
        "product_name": str,
        "quantity": int,
        "unit_price": Decimal,
        "discount_amount": Optional[Decimal],
    }

    Returns:
        Decimal: Calculated tax amount (e.g. 10% standard rate on net price).
    """
    quantity = line.get("quantity", 1)
    unit_price = line.get("unit_price", Decimal("0.00"))
    discount = line.get("discount_amount", Decimal("0.00"))
    line_subtotal = Decimal(quantity) * Decimal(unit_price)
    discounted_subtotal = max(Decimal("0.00"), line_subtotal - Decimal(discount))
    tax_rate = Decimal("0.10")  # 10% default mock tax rate
    return (discounted_subtotal * tax_rate).quantize(Decimal("0.01"))


def get_applicable_discounts(subscription_id: int) -> List[Dict[str, Any]]:
    """
    Retrieve active discounts and promotional codes applicable to a subscription.

    # TODO: Replace stub when service is available.
    Interface owned by Member 2 (catalog, plans, tax rules, discount rules).

    Expected Return Data Structure (Contract):
    [
        {
            "id": int,                   # Primary key of discount/coupon
            "code": str,                 # Coupon/promo code (e.g. "LAUNCH2026")
            "description": str,          # User-friendly description
            "discount_type": str,        # "fixed" or "percentage"
            "value": Decimal,            # Percentage rate or fixed deduction
            "applicable_amount": Decimal # Max or computed discount amount
        }
    ]
    """
    return [
        {
            "id": 1,
            "code": "EARLYBIRD10",
            "description": "10% Early Bird Promotional Discount",
            "discount_type": "percentage",
            "value": Decimal("10.00"),
            "applicable_amount": Decimal("10.00"),
        }
    ]


def redeem(discount_id: int) -> Dict[str, Any]:
    """
    Mark a promotional code or discount as redeemed/applied to prevent re-use.

    # TODO: Replace stub when service is available.
    Interface owned by Member 2 (catalog, plans, tax rules, discount rules).

    Expected Return Data Structure (Contract):
    {
        "discount_id": int,
        "redeemed": bool,
        "redeemed_at": str,
    }
    """
    return {
        "discount_id": discount_id,
        "redeemed": True,
        "message": f"Discount {discount_id} marked as redeemed.",
    }
