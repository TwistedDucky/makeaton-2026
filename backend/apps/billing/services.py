"""
Business logic and write services for billing (invoices, generation).
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Union

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from . import integrations
from .models import (
    IllegalStatusTransitionError,
    Invoice,
    InvoiceDiscount,
    InvoiceLine,
)


@dataclass(frozen=True)
class ConfirmResult:
    """Result returned by confirm_invoice service."""

    invoice: Invoice
    amounts_changed: bool


class _DiscountUsageFailed(Exception):
    """Internal exception raised to trigger atomic rollback when discount redemption fails."""

    def __init__(self, failed_ids: List[int]):
        super().__init__(f"Discount usage recording failed for discount ids: {failed_ids}")
        self.failed_ids = failed_ids


def confirm_invoice(invoice: Union[Invoice, int]) -> ConfirmResult:
    """
    Orchestrate confirmation of a draft invoice with concurrency safety,
    discount redemption, and automatic re-pricing fallback.

    Accepts an Invoice instance or pk.
    Returns ConfirmResult(invoice, amounts_changed: bool).
    """
    invoice_id = invoice.id if isinstance(invoice, Invoice) else int(invoice)

    try:
        with transaction.atomic():
            inv = Invoice.objects.select_for_update().get(pk=invoice_id)
            if inv.status != Invoice.Status.DRAFT:
                raise IllegalStatusTransitionError(
                    f"Cannot confirm invoice {inv.number or inv.id}: current status is '{inv.status}', "
                    f"but only '{Invoice.Status.DRAFT}' invoices can be confirmed."
                )

            distinct_ids = sorted(set(inv.discounts.values_list("discount_id", flat=True)))
            has_line_discounts = inv.lines.filter(discount_amount__gt=Decimal("0.00")).exists()

            if distinct_ids or has_line_discounts:
                if not integrations.USE_REAL_DISCOUNT_USAGE:
                    raise ValidationError(
                        "Cannot confirm invoice with discounts: discount usage recording is disabled "
                        "(USE_REAL_DISCOUNT_USAGE is False)."
                    )

            if distinct_ids:
                res = integrations.redeem_discounts(distinct_ids, inv.id, inv.subscription_id)
                if not res.get("all_recorded", False):
                    raise _DiscountUsageFailed(res.get("failed_ids", []))

            inv.confirm()
            if isinstance(invoice, Invoice) and invoice is not inv:
                invoice.status = inv.status
                invoice.updated_at = inv.updated_at
            return ConfirmResult(invoice=inv, amounts_changed=False)

    except _DiscountUsageFailed:
        if not integrations.USE_REAL_PRICING:
            raise ValidationError(
                "Discount redemption failed and re-pricing is disabled (USE_REAL_PRICING is False)."
            )

        with transaction.atomic():
            inv = Invoice.objects.select_for_update().get(pk=invoice_id)
            if inv.status != Invoice.Status.DRAFT:
                raise IllegalStatusTransitionError(
                    f"Cannot confirm invoice {inv.number or inv.id}: current status is '{inv.status}', "
                    f"but only '{Invoice.Status.DRAFT}' invoices can be confirmed."
                )

            old_total = inv.total

            lines_qs = list(inv.lines.all().order_by("id"))
            lines_data = [
                {
                    "product_id": line.product_id,
                    "variant_id": line.variant_id,
                    "product_name": line.product_name,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,  # frozen unit price from draft
                    "tax_id": line.tax_id,
                }
                for line in lines_qs
            ]
            priced = integrations.price_invoice_lines(lines_data, billing_date=timezone.localdate())

            priced_lines = priced.get("lines", [])
            for line, priced_line in zip(lines_qs, priced_lines):
                line.discount_amount = Decimal(str(priced_line["discount_amount"]))
                line.tax_amount = Decimal(str(priced_line["tax_amount"]))
                line.save()

            discount_totals: Dict[int, Decimal] = {}
            for dl in priced.get("discount_lines", []):
                d_id = dl["discount_id"]
                amt = Decimal(str(dl["amount"]))
                discount_totals[d_id] = discount_totals.get(d_id, Decimal("0.00")) + amt

            inv.discounts.all().delete()
            new_discounts = [
                InvoiceDiscount(invoice=inv, discount_id=d_id, amount=amt)
                for d_id, amt in discount_totals.items()
                if amt > Decimal("0.00")
            ]
            if new_discounts:
                InvoiceDiscount.objects.bulk_create(new_discounts)

            inv.recalculate_totals()
            amounts_changed = (inv.total != old_total)

            new_distinct_ids = sorted(set(inv.discounts.values_list("discount_id", flat=True)))
            if new_distinct_ids:
                res2 = integrations.redeem_discounts(new_distinct_ids, inv.id, inv.subscription_id)
                if not res2.get("all_recorded", False):
                    raise ValidationError("discount no longer available, please retry")

            inv.confirm()
            if isinstance(invoice, Invoice) and invoice is not inv:
                invoice.status = inv.status
                invoice.updated_at = inv.updated_at
                invoice.subtotal = inv.subtotal
                invoice.discount_total = inv.discount_total
                invoice.tax_total = inv.tax_total
                invoice.total = inv.total
            return ConfirmResult(invoice=inv, amounts_changed=amounts_changed)


def cancel_invoice(invoice: Union[Invoice, int]) -> Invoice:
    """
    Cancel a draft or confirmed invoice with row locking.
    Forbidden if payments recorded (amount_paid > 0) or already cancelled/paid.
    """
    invoice_id = invoice.id if isinstance(invoice, Invoice) else int(invoice)
    with transaction.atomic():
        inv = Invoice.objects.select_for_update().get(pk=invoice_id)
        inv.cancel()
        if isinstance(invoice, Invoice) and invoice is not inv:
            invoice.status = inv.status
            invoice.updated_at = inv.updated_at
        return inv
