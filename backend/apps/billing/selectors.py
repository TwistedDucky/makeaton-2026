"""
Queries and read selectors for the billing app.

Note:
All invoice status strings are lowercase: 'draft', 'confirmed', 'paid', 'cancelled'.
"""

from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional

from django.db.models import Count, F, Q, QuerySet, Sum
from django.utils import timezone

from .models import Invoice, quantize_money


def _apply_invoice_filters(
    qs: QuerySet[Invoice],
    filters: Optional[Dict[str, Any]],
) -> QuerySet[Invoice]:
    """Apply common filters (customer_id, due_date_from, due_date_to) to an Invoice QuerySet."""
    if not filters:
        return qs
    if "customer_id" in filters and filters["customer_id"] is not None:
        qs = qs.filter(customer_id=filters["customer_id"])
    if "due_date_from" in filters and filters["due_date_from"] is not None:
        qs = qs.filter(due_date__gte=filters["due_date_from"])
    if "due_date_to" in filters and filters["due_date_to"] is not None:
        qs = qs.filter(due_date__lte=filters["due_date_to"])
    return qs


def outstanding_total(filters: Optional[Dict[str, Any]] = None) -> Decimal:
    """
    Return the sum of outstanding balances (total - amount_paid) over confirmed invoices.

    Status strings are lowercase ('confirmed').
    Uses a single aggregate query without per-row loops.
    """
    qs = Invoice.objects.filter(status=Invoice.Status.CONFIRMED)
    qs = _apply_invoice_filters(qs, filters)
    result = qs.aggregate(outstanding=Sum(F("total") - F("amount_paid")))["outstanding"]
    if result is None:
        return Decimal("0.00")
    return quantize_money(result)


def overdue_invoices(
    as_of: Optional[date] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> QuerySet[Invoice]:
    """
    Return a QuerySet of overdue invoices:
    - Status is 'confirmed' (lowercase)
    - due_date < as_of (boundary: due today is NOT overdue)
    - outstanding > 0 (total > amount_paid)

    as_of defaults to timezone.localdate().
    """
    cutoff = as_of or timezone.localdate()
    qs = Invoice.objects.filter(
        status=Invoice.Status.CONFIRMED,
        due_date__lt=cutoff,
        total__gt=F("amount_paid"),
    )
    return _apply_invoice_filters(qs, filters)


def overdue_total(
    as_of: Optional[date] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> Decimal:
    """
    Return the sum of outstanding balances (total - amount_paid) for overdue invoices.

    Status strings are lowercase ('confirmed').
    Uses a single aggregate query without per-row loops.
    as_of defaults to timezone.localdate().
    """
    qs = overdue_invoices(as_of=as_of, filters=filters)
    result = qs.aggregate(total_overdue=Sum(F("total") - F("amount_paid")))["total_overdue"]
    if result is None:
        return Decimal("0.00")
    return quantize_money(result)


def invoice_counts_by_status(filters: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """
    Return a dictionary mapping each status to the count of invoices.

    Status strings are lowercase ('draft', 'confirmed', 'paid', 'cancelled').
    Uses a single aggregate query with conditional counts.
    """
    qs = Invoice.objects.all()
    qs = _apply_invoice_filters(qs, filters)
    aggregates = {
        status: Count("id", filter=Q(status=status))
        for status in Invoice.Status.values
    }
    return qs.aggregate(**aggregates)
