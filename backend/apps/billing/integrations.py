"""
Integrations and external service adapters for the billing app.

This module acts as the anti-corruption layer and single point of integration
with external domains (apps.subscriptions, apps.catalog, apps.sales).

Integration Architecture & Migration Path:
------------------------------------------
USE_REAL_SUBSCRIPTIONS controls whether get_due_subscriptions and
advance_next_billing_date call Member 3's real implementation in
apps.subscriptions.services or return local typed stubs.

USE_REAL_PRICING controls whether price_invoice_lines calls Member 2's
pricing service in apps.catalog.services or returns local typed stubs.

USE_REAL_DISCOUNT_USAGE controls whether discount usage recording is enabled
with Member 2's catalog domain upon invoice confirmation.
"""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.utils import timezone

from .models import quantize_money

USE_REAL_SUBSCRIPTIONS = True       # True = call apps.subscriptions.services
USE_REAL_PRICING = True             # True = call apps.catalog.services.price_invoice
USE_REAL_DISCOUNT_USAGE = False     # True = call apps.catalog.services.record_discount_usage

DEFAULT_PAYMENT_TERMS_DAYS = 30

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
                    "tax_id": Optional[int],      # Optional Catalog Tax ID
                }
            ],
        }
    ]
    """
    if USE_REAL_SUBSCRIPTIONS:
        from apps.subscriptions.services import (
            get_due_subscriptions as _real_get_due_subscriptions,
        )
        raw_subs = _real_get_due_subscriptions(target_date)
    else:
        billing_date = target_date or timezone.localdate()
        period_start = billing_date.replace(day=1)
        period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        raw_subs = [
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
                        "tax_id": 1,
                    },
                    {
                        "product_id": 2,
                        "variant_id": None,
                        "product_name": "Priority Support Add-on",
                        "quantity": 1,
                        "unit_price": Decimal("20.00"),
                        "tax_id": None,
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
                        "tax_id": 2,
                    }
                ],
            },
        ]

    normalized_subs: List[Dict[str, Any]] = []
    for sub in raw_subs:
        sub_id = sub.get("id")
        period_start = sub.get("period_start")
        period_end = sub.get("period_end")

        if not period_start or not period_end:
            raise ValueError(
                f"Subscription {sub_id} missing period_start or period_end"
            )

        new_lines = [
            {**line, "variant_id": line.get("variant_id")}
            for line in sub.get("lines") or []
        ]

        norm_item: Dict[str, Any] = {
            **sub,
            "lines": new_lines,
        }
        if "payment_terms_days" in sub:
            norm_item["payment_terms_days"] = sub["payment_terms_days"]

        normalized_subs.append(norm_item)

    return normalized_subs


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
    if USE_REAL_SUBSCRIPTIONS:
        from apps.subscriptions.services import (
            advance_next_billing_date as _real_advance_next_billing_date,
        )
        res = dict(_real_advance_next_billing_date(subscription_id))
        res["status"] = str(res.get("status", "")).upper()
        return res

    return {
        "subscription_id": subscription_id,
        "next_billing_date": timezone.localdate() + timedelta(days=30),
        "status": "ACTIVE",
    }


def price_invoice_lines(
    lines: List[Dict[str, Any]],
    billing_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Unified pricing adapter providing pricing and tax calculation for invoice lines.

    If USE_REAL_PRICING is True, invokes apps.catalog.services.price_invoice.
    Otherwise, returns fallback typed calculation while in development.

    Guard:
    If either stub flag (USE_REAL_PRICING or USE_REAL_DISCOUNT_USAGE) is False
    and settings.DEBUG is False, raises RuntimeError.
    """
    if (not USE_REAL_PRICING or not USE_REAL_DISCOUNT_USAGE) and not getattr(settings, "DEBUG", True):
        raise RuntimeError(
            "Stub pricing cannot be used in production (DEBUG=False). "
            "Real pricing and discount usage services must be enabled."
        )

    if USE_REAL_PRICING:
        from apps.catalog.services import Line, price_invoice

        catalog_lines = [
            Line(
                product_id=item["product_id"],
                quantity=item.get("quantity", 1),
                unit_price=Decimal(str(item.get("unit_price", "0.00"))),
                tax_id=item.get("tax_id"),
            )
            for item in lines
        ]
        pricing_date = billing_date or timezone.localdate()
        priced_invoice = price_invoice(catalog_lines, pricing_date)

        mapped_lines = [
            {
                "product_id": line.product_id,
                "variant_id": item.get("variant_id"),
                "product_name": item.get("product_name", ""),
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "discount_amount": line.line_discount,
                "tax_amount": line.tax_amount,
                "tax_id": line.tax_id,
                "line_total": quantize_money(line.net + line.tax_amount),
            }
            for line, item in zip(priced_invoice.lines, lines)
        ]

        mapped_discounts = [
            {
                "discount_id": dl.discount_id,
                "description": dl.description,
                "amount": abs(dl.amount),
                "line_index": dl.line_index,
            }
            for dl in priced_invoice.discount_lines
        ]

        return {
            "lines": mapped_lines,
            "discount_lines": mapped_discounts,
            "totals": {
                "subtotal": priced_invoice.subtotal,
                "discount_total": priced_invoice.discount_total,
                "tax_total": priced_invoice.tax_total,
                "total": priced_invoice.total,
            },
        }

    # Fallback typed stub calculation
    priced_lines = []
    discount_lines = []
    subtotal = Decimal("0.00")
    discount_total = Decimal("0.00")
    tax_total = Decimal("0.00")

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
        tax_amount = (discounted_sub * Decimal("0.10")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        line_total = (discounted_sub + tax_amount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        priced_lines.append({
            "product_id": item.get("product_id"),
            "variant_id": item.get("variant_id"),
            "product_name": item.get("product_name", ""),
            "quantity": int(qty),
            "unit_price": unit_price.quantize(TWOPLACES, rounding=ROUND_HALF_UP),
            "discount_id": discount_id,
            "discount_amount": discount_amount,
            "tax_amount": tax_amount,
            "tax_id": item.get("tax_id"),
            "line_total": line_total,
        })

        if discount_id and discount_amount > Decimal("0.00"):
            discount_lines.append({
                "discount_id": discount_id,
                "description": "10% Early Bird Promotional Discount",
                "amount": discount_amount,
                "line_index": idx,
            })

        subtotal += line_subtotal
        discount_total += discount_amount
        tax_total += tax_amount

    total = (subtotal - discount_total + tax_total).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    return {
        "lines": priced_lines,
        "discount_lines": discount_lines,
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
) -> Dict[str, Any]:
    """
    Record discount usage once an invoice is confirmed.
    Usage is recorded at invoice CONFIRM.

    Deduplicates discount_ids in sorted ascending order to prevent deadlocks.
    When USE_REAL_DISCOUNT_USAGE is True, invokes apps.catalog.services.record_discount_usage
    once per discount ID.
    Returns:
        {"all_recorded": bool, "failed_ids": [int, ...]}
    """
    distinct_ids = sorted(set(discount_ids))

    if USE_REAL_DISCOUNT_USAGE:
        from apps.catalog.services import record_discount_usage

        failed_ids: List[int] = []
        for d_id in distinct_ids:
            success = record_discount_usage(d_id, invoice_id, subscription_id)
            if not success:
                failed_ids.append(d_id)

        return {
            "all_recorded": len(failed_ids) == 0,
            "failed_ids": failed_ids,
        }

    return {
        "all_recorded": True,
        "failed_ids": [],
    }
