"""
Business logic and write services for payments and allocations.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Payment, PaymentAllocation


def _parse_money(value: Any, field: str) -> Decimal:
    """
    Parse a monetary value into a Decimal with at most 2 decimal places.
    Converts via Decimal(str(v)), catches InvalidOperation, requires is_finite(),
    rejects values whose absolute value does not fit Payment.amount, accepts trailing zeros
    like "1.500" by normalizing before the decimal-places check, and raises ValidationError on failure.
    """
    if value is None or isinstance(value, bool):
        raise ValidationError({field: f"Invalid {field} value: must be a valid number."})

    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field: f"Invalid {field} value '{value}': not a valid decimal number."})

    if not d.is_finite():
        raise ValidationError({field: f"Invalid {field} value '{value}': must be finite."})

    field_meta = Payment._meta.get_field("amount")
    max_digits = field_meta.max_digits
    decimal_places = field_meta.decimal_places
    max_whole_digits = max_digits - decimal_places

    if abs(d) >= Decimal(10) ** max_whole_digits:
        raise ValidationError(
            {field: f"Invalid {field} value '{value}': value too large to fit in field."}
        )

    # Accept trailing zeros like "1.500" by normalizing before the decimal-places check
    norm_d = d.normalize()
    if norm_d.as_tuple().exponent < -decimal_places:
        raise ValidationError(
            {field: f"Invalid {field} value '{value}': exceeds maximum of {decimal_places} decimal places."}
        )

    return d.quantize(Decimal("0.01"))


def record_payment(
    *,
    customer_id: Any,
    method: str,
    amount: Any,
    payment_date: Optional[date] = None,
    allocations: List[Dict[str, Any]],
    note: str = "",
    recorded_by: Optional[Any] = None,
) -> Payment:
    """
    Record a customer payment and allocate it across one or more confirmed invoices.

    Enforces all domain integrity rules inside a single atomic transaction:
    - customer_id coerced to int up front (rejects bool, float, non-numeric).
    - recorded_by is required (accepts user instance or int id).
    - Strictly positive payment amount parsed with at most 2 decimal places.
    - Allowed payment method choices.
    - Non-empty allocations list with no duplicate invoice IDs.
    - Every allocation amount strictly positive with at most 2 decimal places.
    - Sum of allocation amounts equals payment amount exactly.
    - Row-level locking on target invoices in ascending ID order to prevent deadlocks.
    - Every invoice must belong to the same customer.
    - Target invoices must be in 'confirmed' status (rejects draft, paid, cancelled).
    - Allocation amount cannot exceed an invoice's outstanding balance (total - amount_paid).
    - Increases invoice amount_paid, and marks invoice as paid if amount_paid >= total.
    """
    if customer_id is None or isinstance(customer_id, (bool, float)):
        raise ValidationError(
            {"customer_id": f"Invalid customer_id '{customer_id}': must be an integer."}
        )
    try:
        customer_id = int(customer_id)
    except (TypeError, ValueError):
        raise ValidationError(
            {"customer_id": f"Invalid customer_id '{customer_id}': must be an integer."}
        )

    if recorded_by is None:
        raise ValidationError({"recorded_by": "recorded_by is required."})

    if hasattr(recorded_by, "id"):
        recorded_by_id = recorded_by.id
    else:
        try:
            if isinstance(recorded_by, bool):
                raise ValueError()
            recorded_by_id = int(recorded_by)
        except (TypeError, ValueError):
            raise ValidationError({"recorded_by": "Invalid recorded_by identifier."})

    amount = _parse_money(amount, "amount")
    if amount <= Decimal("0.00"):
        raise ValidationError({"amount": "Payment amount must be greater than zero."})

    if method not in Payment.Method.values:
        raise ValidationError(
            {"method": f"Invalid payment method '{method}'. Allowed choices: {Payment.Method.values}"}
        )

    if not allocations or not isinstance(allocations, list):
        raise ValidationError({"allocations": "Allocations list must not be empty."})

    seen_invoice_ids = set()
    total_allocated = Decimal("0.00")
    normalized_allocations = []

    for alloc in allocations:
        if not isinstance(alloc, dict) or "invoice_id" not in alloc or "amount" not in alloc:
            raise ValidationError(
                {"allocations": "Each allocation must contain 'invoice_id' and 'amount'."}
            )

        raw_inv_id = alloc["invoice_id"]
        if isinstance(raw_inv_id, (bool, float)):
            raise ValidationError(
                {"allocations": f"Invalid invoice_id '{raw_inv_id}': must be an integer."}
            )
        try:
            inv_id = int(raw_inv_id)
        except (TypeError, ValueError):
            raise ValidationError(
                {"allocations": f"Invalid invoice_id '{raw_inv_id}': must be an integer."}
            )

        if inv_id in seen_invoice_ids:
            raise ValidationError(
                {"allocations": f"Duplicate invoice_id {inv_id} in allocations."}
            )
        seen_invoice_ids.add(inv_id)

        alloc_amt = _parse_money(alloc["amount"], "allocations")
        if alloc_amt <= Decimal("0.00"):
            raise ValidationError(
                {"allocations": f"Allocation amount for invoice {inv_id} must be greater than zero."}
            )
        total_allocated += alloc_amt

        normalized_allocations.append({
            "invoice_id": inv_id,
            "amount": alloc_amt,
        })

    if total_allocated != amount:
        raise ValidationError(
            {
                "allocations": (
                    f"Sum of allocations ({total_allocated}) does not match "
                    f"payment amount ({amount}) exactly."
                )
            }
        )

    with transaction.atomic():
        # Lazy-import billing models inside service function
        from apps.billing.models import Invoice, quantize_money

        sorted_ids = sorted(seen_invoice_ids)
        locked_invoices = list(
            Invoice.objects.select_for_update().filter(id__in=sorted_ids).order_by("id")
        )
        if len(locked_invoices) != len(sorted_ids):
            found_ids = {inv.id for inv in locked_invoices}
            missing_ids = set(sorted_ids) - found_ids
            raise ValidationError({"allocations": f"Invoices not found: {missing_ids}"})

        invoice_map = {inv.id: inv for inv in locked_invoices}

        for alloc in normalized_allocations:
            inv = invoice_map[alloc["invoice_id"]]
            alloc_amt = alloc["amount"]

            if inv.customer_id != customer_id:
                raise ValidationError(
                    f"Invoice {inv.id} belongs to customer {inv.customer_id}, "
                    f"but payment is for customer {customer_id}."
                )

            if inv.status != Invoice.Status.CONFIRMED:
                raise ValidationError(
                    f"Cannot allocate payment to invoice {inv.id}: status is '{inv.status}', "
                    f"but only '{Invoice.Status.CONFIRMED}' invoices can receive payments."
                )

            outstanding = inv.total - inv.amount_paid
            if alloc_amt > outstanding:
                raise ValidationError(
                    f"Allocation amount {alloc_amt} exceeds outstanding balance {outstanding} "
                    f"for invoice {inv.id}."
                )

        payment = Payment.objects.create(
            customer_id=customer_id,
            method=method,
            amount=amount,
            payment_date=payment_date or timezone.localdate(),
            note=note,
            recorded_by_id=recorded_by_id,
        )

        for alloc in normalized_allocations:
            inv = invoice_map[alloc["invoice_id"]]
            alloc_amt = alloc["amount"]

            PaymentAllocation.objects.create(
                payment=payment,
                invoice=inv,
                amount=alloc_amt,
            )

            inv.amount_paid = quantize_money(inv.amount_paid + alloc_amt)
            inv.save(update_fields=["amount_paid", "updated_at"])

            if inv.amount_paid >= inv.total:
                inv.mark_paid()

        return payment


def mark_zero_total_invoice_paid(invoice_id: int) -> Any:
    """
    Mark a zero-total confirmed invoice as paid directly without allocations or payment record.
    Requires status == confirmed and total == 0 after the lock, else ValidationError.
    Catches Invoice.DoesNotExist and raises ValidationError.
    """
    from apps.billing.models import Invoice

    with transaction.atomic():
        try:
            invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
        except Invoice.DoesNotExist:
            raise ValidationError(f"Invoice with id {invoice_id} does not exist.")

        if invoice.status != Invoice.Status.CONFIRMED:
            raise ValidationError(
                f"Cannot mark invoice {invoice.id} paid via zero-total helper: status is '{invoice.status}', "
                f"but only '{Invoice.Status.CONFIRMED}' invoices can be marked paid."
            )
        if invoice.total != Decimal("0.00"):
            raise ValidationError(
                f"Cannot mark invoice {invoice.id} paid via zero-total helper: total is {invoice.total}."
            )
        invoice.mark_paid()
        return invoice
