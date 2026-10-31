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


def get_due_subscriptions(target_date: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    Fetch all active subscriptions due for billing on or before target_date.

    # TODO: Replace stub when service is available.
    Interface owned by Member 3 (subscription state machine and quotations).

    Expected Return Data Structure (Contract):
    [
        {
            "id": int,                     # Primary key of Subscription
            "customer_id": int,            # Primary key of User (accounts.User)
            "period_start": date,          # Start of this billing period (inclusive)
            "period_end": date,            # End of this billing period (inclusive)
            "lines": [                     # Line items to be billed
                {
                    "product_id": int,     # ID of the plan/add-on product in catalog
                    "product_name": str,   # Display name (e.g. "Standard Subscription")
                    "quantity": int,       # Quantity (e.g. 1)
                    "unit_price": Decimal, # Unit price (e.g. Decimal("50.00"))
                }
            ],
        }
    ]
    """
    billing_date = target_date or date.today()
    period_start = billing_date.replace(day=1)
    # Approximate end of month
    period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    return [
        {
            "id": 101,
            "customer_id": 1,
            "period_start": period_start,
            "period_end": period_end,
            "lines": [
                {
                    "product_id": 1,
                    "product_name": "Premium Plan Monthly",
                    "quantity": 1,
                    "unit_price": Decimal("99.00"),
                },
                {
                    "product_id": 2,
                    "product_name": "Additional Storage 50GB",
                    "quantity": 2,
                    "unit_price": Decimal("10.00"),
                },
            ],
        },
        {
            "id": 102,
            "customer_id": 2,
            "period_start": period_start,
            "period_end": period_end,
            "lines": [
                {
                    "product_id": 3,
                    "product_name": "Basic Plan Monthly",
                    "quantity": 1,
                    "unit_price": Decimal("29.00"),
                }
            ],
        },
    ]


def advance_next_billing_date(subscription_id: int) -> Dict[str, Any]:
    """
    Advance the subscription's next_billing_date to the next cycle.

    # TODO: Replace stub when service is available.
    Interface owned by Member 3 (subscription state machine and quotations).

    Expected Return Data Structure (Contract):
    {
        "subscription_id": int,
        "next_billing_date": date,
        "status": str,  # "active", "updated"
    }
    """
    return {
        "subscription_id": subscription_id,
        "next_billing_date": date.today() + timedelta(days=30),
        "status": "updated",
    }


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
