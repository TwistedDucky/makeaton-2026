"""
Integrations and external service adapters for the billing app.

This module acts as the anti-corruption layer and single point of integration
with external domains (apps.subscriptions, apps.catalog, apps.sales).

Integration Architecture & Migration Path:
------------------------------------------
USE_REAL_SERVICES is a feature flag. When False (current state), this module
returns realistic mock data conforming strictly to agreed teammate contracts.
When True (future integration task once teammates merge their service modules),
the functions in this module will import and invoke the real services:
- apps.subscriptions.services.get_due_subscriptions
- apps.subscriptions.services.advance_next_billing_date
- apps.catalog.services.price_invoice (once implemented by Member 2)
- apps.catalog.services.record_discount_usage (once implemented by Member 2)
"""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

USE_REAL_SERVICES = False
TWOPLACES = Decimal("0.01")


def get_due_subscriptions(target_date: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    Fetch active subscriptions due for billing on or before target_date.

    Contract with Member 3 (apps.subscriptions.services):
    - Multi-period rule: Returns exactly ONE period per subscription per invocation (oldest due period first).
      Subsequent missed periods are retrieved on successive billing cycles after advance_next_billing_date() is called.
    - Currency: Platform is strictly single-currency. No currency field is present.
    - Pricing: `unit_price` on each line item already includes any variant price adjustments.

    Expected Return Structure:
    [
        {
            "id": int,                     # Primary key of Subscription
            "customer_id": int,            # Primary key of User (accounts.User)
            "period_start": date,          # Start date of this billing period (inclusive)
            "period_end": date,            # End date of this billing period (inclusive)
            "lines": [
                {
                    "product_id": int,            # Catalog Product ID
                    "variant_id": Optional[int],  # Optional Catalog ProductVariant ID
                    "product_name": str,          # Descriptive display name (e.g. "Plan - Variant")
                    "quantity": int,              # Line quantity
                    "unit_price": Decimal,        # Unit price (including variant extra_price)
                }
            ],
        }
    ]
    """
    if USE_REAL_SERVICES:
        # TODO: Wire to `from apps.subscriptions.services import get_due_subscriptions as _get_due`
        pass

    billing_date = target_date or date.today()
    period_start = billing_date.replace(day=1)
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
                    "variant_id": 10,
                    "product_name": "Premium Cloud Suite - 50GB",
                    "quantity": 1,
                    "unit_price": Decimal("99.00"),
                },
                {
                    "product_id": 2,
                    "variant_id": None,
                    "product_name": "Priority Support Add-on",
                    "quantity": 1,
                    "unit_price": Decimal("20.00"),
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
                    "variant_id": None,
                    "product_name": "Standard Plan Monthly",
                    "quantity": 1,
                    "unit_price": Decimal("30.00"),
                }
            ],
        },
    ]


def advance_next_billing_date(subscription_id: int) -> Dict[str, Any]:
    """
    Advance subscription's billing schedule by one billing period.

    Contract with Member 3 (apps.subscriptions.services):
    - Idempotent and safe to invoke after successful invoice creation.
    - Updates subscription.current_period_start, current_period_end, and next_billing_date.
    - If plan.auto_close is true and expiry_date has passed, marks subscription as CLOSED.

    Expected Return Structure:
    {
        "subscription_id": int,
        "next_billing_date": date,
        "status": str,  # e.g. "ACTIVE" or "CLOSED"
    }
    """
    if USE_REAL_SERVICES:
        # TODO: Wire to `from apps.subscriptions.services import advance_next_billing_date as _advance`
        pass

    return {
        "subscription_id": subscription_id,
        "next_billing_date": date.today() + timedelta(days=30),
        "status": "ACTIVE",
    }


def price_invoice_lines(
    lines: List[Dict[str, Any]],
    billing_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Unified pricing adapter providing pure calculation for invoice lines.

    Contract with Member 2 (apps.catalog):
    - Pure Calculation: MUST NOT record DiscountUsage or mutate database state.
      Previewing or draft generation must not consume promotional usage limits.
    - Discounts: Applies eligible discounts by product or subscription scope.
      Discount cannot exceed line subtotal.
    - Taxes: Tax is computed on the discounted amount (line_subtotal - discount_amount).
    - Rounding: All money fields quantized to 2 decimal places with ROUND_HALF_UP.

    Input Lines Structure:
    [
        {
            "product_id": int,
            "variant_id": Optional[int],
            "product_name": str,
            "quantity": int,
            "unit_price": Decimal,
        }
    ]

    Expected Return Structure:
    {
        "lines": [
            {
                "product_id": int,
                "variant_id": Optional[int],
                "discount_id": Optional[int],  # Populated if a catalog discount applied
                "discount_amount": Decimal,
                "tax_amount": Decimal,
                "line_total": Decimal,
            }
        ],
        "totals": {
            "subtotal": Decimal,
            "discount_total": Decimal,
            "tax_total": Decimal,
            "total": Decimal,
        }
    }
    """
    if USE_REAL_SERVICES:
        # TODO: Wire to Member 2's `apps.catalog.services.price_invoice`
        pass

    priced_lines = []
    subtotal = Decimal("0.00")
    discount_total = Decimal("0.00")
    tax_total = Decimal("0.00")

    # Standard mock calculation: 10% discount on first line (if applicable), 10% tax on net
    for idx, item in enumerate(lines):
        qty = Decimal(item.get("quantity", 1))
        unit_price = Decimal(str(item.get("unit_price", "0.00")))
        line_subtotal = (qty * unit_price).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        # Mock: 10% promo discount on first line only
        discount_id = 1 if idx == 0 and line_subtotal > Decimal("0.00") else None
        discount_amount = (
            (line_subtotal * Decimal("0.10")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
            if discount_id
            else Decimal("0.00")
        )

        discounted_sub = max(Decimal("0.00"), line_subtotal - discount_amount)
        # Mock 10% tax rate on discounted amount
        tax_amount = (discounted_sub * Decimal("0.10")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        line_total = (discounted_sub + tax_amount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        priced_lines.append({
            "product_id": item.get("product_id"),
            "variant_id": item.get("variant_id"),
            "discount_id": discount_id,
            "discount_amount": discount_amount,
            "tax_amount": tax_amount,
            "line_total": line_total,
        })

        subtotal += line_subtotal
        discount_total += discount_amount
        tax_total += tax_amount

    total = (subtotal - discount_total + tax_total).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    return {
        "lines": priced_lines,
        "totals": {
            "subtotal": subtotal,
            "discount_total": discount_total,
            "tax_total": tax_total,
            "total": total,
        },
    }


def redeem_discounts(
    discount_ids: List[int],
    invoice_id: int,
    subscription_id: int,
) -> List[Dict[str, Any]]:
    """
    Record discount usage once an invoice is confirmed.

    Contract with Member 2 (apps.catalog):
    - Separate State Mutation: Records DiscountUsage rows (fields: discount, invoice_id, subscription_id)
      and increments Discount.used_count.
    - Executed strictly upon invoice confirmation, never during draft preview.

    Expected Return Structure:
    [
        {
            "discount_id": int,
            "invoice_id": int,
            "recorded": bool,
        }
    ]
    """
    if USE_REAL_SERVICES:
        # TODO: Wire to Member 2's `apps.catalog.services.record_discount_usage`
        pass

    return [
        {
            "discount_id": d_id,
            "invoice_id": invoice_id,
            "recorded": True,
        }
        for d_id in discount_ids
    ]
