"""
Business logic and write services for billing (invoices, generation).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from . import integrations
from .models import (
    IllegalStatusTransitionError,
    Invoice,
    InvoiceDiscount,
    InvoiceLine,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConfirmResult:
    """Result returned by confirm_invoice service."""

    invoice: Invoice
    amounts_changed: bool


@dataclass(frozen=True)
class GenerationSummary:
    """Summary returned by generate_invoices service."""

    created: int
    skipped_existing: int
    advanced: int
    errors: list[dict]
    capped: list[int]


def summary_as_dict(summary: GenerationSummary) -> dict:
    """Convert a GenerationSummary to a JSON-safe dictionary."""
    errors_list = []
    for err in summary.errors:
        p_start = err.get("period_start")
        if hasattr(p_start, "isoformat"):
            p_start_str = p_start.isoformat()
        elif p_start is not None:
            p_start_str = str(p_start)
        else:
            p_start_str = ""

        msg = err.get("message")
        if msg is None:
            msg = err.get("error", "")

        errors_list.append({
            "subscription_id": int(err.get("subscription_id", 0)),
            "period_start": p_start_str,
            "message": str(msg),
        })

    return {
        "created": int(summary.created),
        "skipped_existing": int(summary.skipped_existing),
        "advanced": int(summary.advanced),
        "capped": [int(x) for x in summary.capped],
        "errors": errors_list,
    }


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


def generate_invoices(
    target_date: Optional[date] = None,
    max_periods_per_subscription: int = 24,
) -> GenerationSummary:
    """
    Generate recurring draft invoices for all due subscriptions.

    - Exactly one top-level transaction.atomic() per subscription period.
    - Repeatedly polls get_due_subscriptions until no more periods can be processed.
    - Handles existing active invoices (skipped and advanced).
    - Races handled gracefully via savepoint catching IntegrityError.
    - Subscriptions with no lines or errors are isolated, logged, and excluded from re-poll.
    - Never confirms invoices; generated invoices remain in DRAFT status.
    """
    eval_date = target_date or timezone.localdate()

    created_count = 0
    skipped_count = 0
    advanced_count = 0
    errors: List[Dict[str, Any]] = []
    capped: List[int] = []
    capped_subs: Set[int] = set()
    errored_subs: Set[int] = set()
    periods_count_by_sub: Dict[int, int] = defaultdict(int)
    advanced_keys: Set[Tuple[int, Any]] = set()

    while True:
        due_subs = integrations.get_due_subscriptions(eval_date)

        # A subscription goes into capped (once) only when it has already processed
        # max_periods_per_subscription periods AND the re-poll still returns it as due.
        for sub in due_subs:
            s_id = sub.get("id")
            if (
                s_id is not None
                and s_id not in errored_subs
                and s_id not in capped_subs
                and periods_count_by_sub[s_id] >= max_periods_per_subscription
            ):
                capped_subs.add(s_id)
                capped.append(s_id)

        active_due = [
            s
            for s in due_subs
            if s.get("id") not in errored_subs and s.get("id") not in capped_subs
        ]
        if not active_due:
            break

        processed_any = False
        for sub in active_due:
            sub_id = sub.get("id")
            if sub_id in errored_subs or sub_id in capped_subs:
                continue

            period_start = sub.get("period_start")
            period_end = sub.get("period_end")
            customer_id = sub.get("customer_id")
            lines = sub.get("lines") or []

            # Guard against infinite loop if same (sub_id, period_start) returns after advance
            if (sub_id, period_start) in advanced_keys:
                err_msg = (
                    f"Subscription {sub_id} returned same period_start {period_start} after advance"
                )
                logger.error(err_msg)
                errors.append({
                    "subscription_id": sub_id,
                    "period_start": period_start,
                    "error": err_msg,
                })
                errored_subs.add(sub_id)
                continue

            # Check if capped
            if periods_count_by_sub[sub_id] >= max_periods_per_subscription:
                if sub_id not in capped_subs:
                    capped_subs.add(sub_id)
                    capped.append(sub_id)
                continue

            # Subscription with no lines
            if not lines:
                err_msg = "no lines"
                logger.error("Subscription %s period %s has no lines", sub_id, period_start)
                errors.append({
                    "subscription_id": sub_id,
                    "period_start": period_start,
                    "error": err_msg,
                })
                errored_subs.add(sub_id)
                continue

            try:
                invoice_created = False
                is_skipped = False
                issue_date = timezone.localdate()

                with transaction.atomic():
                    existing_invoice = (
                        Invoice.objects.filter(
                            subscription_id=sub_id,
                            period_start=period_start,
                        )
                        .exclude(status=Invoice.Status.CANCELLED)
                        .first()
                    )

                    if existing_invoice:
                        is_skipped = True
                    else:
                        priced = integrations.price_invoice_lines(
                            lines, billing_date=issue_date
                        )
                        try:
                            with transaction.atomic():
                                terms_days = sub.get("payment_terms_days")
                                if terms_days is None:
                                    terms_days = integrations.DEFAULT_PAYMENT_TERMS_DAYS
                                else:
                                    terms_days = int(terms_days)

                                due_date = issue_date + timedelta(days=terms_days)

                                invoice = Invoice.objects.create(
                                    customer_id=customer_id,
                                    subscription_id=sub_id,
                                    period_start=period_start,
                                    period_end=period_end,
                                    issue_date=issue_date,
                                    due_date=due_date,
                                    status=Invoice.Status.DRAFT,
                                )

                                line_objs = []
                                for pl in priced.get("lines", []):
                                    qty = pl.get("quantity", 1)
                                    u_price = Decimal(str(pl.get("unit_price", "0.00")))
                                    d_amt = Decimal(str(pl.get("discount_amount", "0.00")))
                                    t_amt = Decimal(str(pl.get("tax_amount", "0.00")))
                                    l_tot = pl.get("line_total")
                                    if l_tot is None:
                                        l_tot = (Decimal(qty) * u_price - d_amt + t_amt).quantize(
                                            Decimal("0.01"), rounding=ROUND_HALF_UP
                                        )
                                    else:
                                        l_tot = Decimal(str(l_tot)).quantize(
                                            Decimal("0.01"), rounding=ROUND_HALF_UP
                                        )

                                    line_objs.append(
                                        InvoiceLine(
                                            invoice=invoice,
                                            product_id=pl.get("product_id"),
                                            variant_id=pl.get("variant_id"),
                                            product_name=pl.get("product_name", ""),
                                            quantity=qty,
                                            unit_price=u_price,
                                            discount_amount=d_amt,
                                            tax_amount=t_amt,
                                            tax_id=pl.get("tax_id"),
                                            line_total=l_tot,
                                        )
                                    )
                                InvoiceLine.objects.bulk_create(line_objs)

                                discount_totals: Dict[int, Decimal] = {}
                                for dl in priced.get("discount_lines", []):
                                    d_id = dl["discount_id"]
                                    amt = Decimal(str(dl["amount"]))
                                    discount_totals[d_id] = (
                                        discount_totals.get(d_id, Decimal("0.00")) + amt
                                    )

                                disc_objs = [
                                    InvoiceDiscount(invoice=invoice, discount_id=d_id, amount=amt)
                                    for d_id, amt in discount_totals.items()
                                    if amt > Decimal("0.00")
                                ]
                                if disc_objs:
                                    InvoiceDiscount.objects.bulk_create(disc_objs)

                                invoice.recalculate_totals()

                                priced_totals = priced.get("totals", {})
                                exp_total = Decimal(str(priced_totals.get("total", "0.00")))
                                exp_disc_total = Decimal(
                                    str(priced_totals.get("discount_total", "0.00"))
                                )
                                sum_disc = sum((d.amount for d in disc_objs), Decimal("0.00"))

                                if invoice.total != exp_total:
                                    raise ValidationError(
                                        f"Invoice total mismatch: {invoice.total} != {exp_total}"
                                    )
                                if invoice.discount_total != exp_disc_total:
                                    raise ValidationError(
                                        f"Invoice discount_total mismatch: {invoice.discount_total} != {exp_disc_total}"
                                    )
                                if sum_disc != invoice.discount_total:
                                    raise ValidationError(
                                        f"InvoiceDiscount sum mismatch: {sum_disc} != {invoice.discount_total}"
                                    )

                                invoice_created = True
                                is_skipped = False
                        except IntegrityError:
                            is_skipped = True
                            invoice_created = False

                    # Advance subscription in the same top-level atomic block
                    integrations.advance_next_billing_date(sub_id)

                # Committed successfully
                if invoice_created:
                    created_count += 1
                if is_skipped:
                    skipped_count += 1

                advanced_count += 1
                processed_any = True
                advanced_keys.add((sub_id, period_start))
                periods_count_by_sub[sub_id] += 1
            except Exception as exc:
                logger.exception(
                    "Error generating invoice for subscription %s period %s: %s",
                    sub_id,
                    period_start,
                    exc,
                )
                errors.append({
                    "subscription_id": sub_id,
                    "period_start": period_start,
                    "error": str(exc),
                })
                errored_subs.add(sub_id)

        if not processed_any:
            break

    return GenerationSummary(
        created=created_count,
        skipped_existing=skipped_count,
        advanced=advanced_count,
        errors=errors,
        capped=capped,
    )
