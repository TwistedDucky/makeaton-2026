"""
Queries and read selectors for the payments app.

Note:
All invoice status strings are lowercase: 'draft', 'confirmed', 'paid', 'cancelled'.
"""

from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional

from django.db.models import Sum

from .models import PaymentAllocation


def revenue_between(
    start: date,
    end: date,
    filters: Optional[Dict[str, Any]] = None,
) -> Decimal:
    """
    Calculate total revenue between start and end dates (inclusive).

    Sum of PaymentAllocation.amount for allocations whose payment's payment_date
    is within the range [start, end], excluding allocations linked to cancelled invoices.

    Status strings are lowercase ('cancelled').
    Uses a single aggregate query without per-row loops.
    """
    qs = PaymentAllocation.objects.filter(
        payment__payment_date__gte=start,
        payment__payment_date__lte=end,
    ).exclude(invoice__status="cancelled")

    if filters:
        if "customer_id" in filters and filters["customer_id"] is not None:
            qs = qs.filter(payment__customer_id=filters["customer_id"])
        if "due_date_from" in filters and filters["due_date_from"] is not None:
            qs = qs.filter(invoice__due_date__gte=filters["due_date_from"])
        if "due_date_to" in filters and filters["due_date_to"] is not None:
            qs = qs.filter(invoice__due_date__lte=filters["due_date_to"])

    result = qs.aggregate(revenue=Sum("amount"))["revenue"]
    if result is None:
        return Decimal("0.00")
    return Decimal(str(result)).quantize(Decimal("0.01"))
