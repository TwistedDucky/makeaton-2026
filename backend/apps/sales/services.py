from datetime import timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    QuotationTemplate,
    QuotationTemplateLine,
    Quotation,
    QuotationLine,
)


@transaction.atomic
def create_quotation_from_template(
    template_id: int,
    customer_id: int,
    sales_rep_id: int = None,
    notes: str = "",
) -> Quotation:
    """
    Creates a new Quotation pre-filled with the plan, product lines,
    payment terms, and validity period defined on a QuotationTemplate.
    """
    template = QuotationTemplate.objects.select_related("plan").prefetch_related("lines__product__tax", "lines__variant").get(pk=template_id)

    if not template.is_active:
        raise ValidationError("Cannot create quotation from an inactive template.")

    today = timezone.now().date()
    valid_until = today + timedelta(days=template.validity_days)

    quotation = Quotation.objects.create(
        customer_id=customer_id,
        sales_rep_id=sales_rep_id,
        template=template,
        plan=template.plan,
        valid_until=valid_until,
        payment_terms=template.payment_terms,
        notes=notes or template.description,
    )

    for t_line in template.lines.all():
        product = t_line.product
        variant = t_line.variant

        # Calculate unit price (use custom override if specified on template, else product + variant)
        if t_line.unit_price is not None:
            unit_price = t_line.unit_price
        else:
            unit_price = product.sales_price
            if variant and variant.extra_price:
                unit_price += variant.extra_price

        # Calculate line tax if product has an associated tax rate
        tax_amount = Decimal("0.00")
        if product.tax and product.tax.is_active:
            if product.tax.kind == "percent":
                tax_amount = (unit_price * Decimal(t_line.quantity) * (product.tax.rate / Decimal("100.00"))).quantize(Decimal("0.01"))
            elif product.tax.kind == "fixed":
                tax_amount = (product.tax.rate * Decimal(t_line.quantity)).quantize(Decimal("0.01"))

        QuotationLine.objects.create(
            quotation=quotation,
            product=product,
            variant=variant,
            quantity=t_line.quantity,
            unit_price=unit_price,
            taxes=tax_amount,
        )

    quotation.recalculate_totals()
    return quotation


def send_quotation(quotation_id: int) -> Quotation:
    quotation = Quotation.objects.get(pk=quotation_id)
    if quotation.status not in [Quotation.Status.DRAFT, Quotation.Status.SENT]:
        raise ValidationError(f"Cannot send quotation in {quotation.status} status.")
    if quotation.is_expired():
        quotation.status = Quotation.Status.EXPIRED
        quotation.save(update_fields=["status", "updated_at"])
        raise ValidationError("Quotation validity period has expired.")

    quotation.status = Quotation.Status.SENT
    quotation.save(update_fields=["status", "updated_at"])
    return quotation


def accept_quotation(quotation_id: int) -> Quotation:
    quotation = Quotation.objects.get(pk=quotation_id)
    if quotation.is_expired():
        quotation.status = Quotation.Status.EXPIRED
        quotation.save(update_fields=["status", "updated_at"])
        raise ValidationError("Quotation has expired and cannot be accepted.")

    if quotation.status in [Quotation.Status.DECLINED, Quotation.Status.EXPIRED, Quotation.Status.CONVERTED]:
        raise ValidationError(f"Cannot accept quotation in {quotation.status} status.")

    quotation.status = Quotation.Status.ACCEPTED
    quotation.save(update_fields=["status", "updated_at"])
    return quotation


def decline_quotation(quotation_id: int, reason: str = "") -> Quotation:
    quotation = Quotation.objects.get(pk=quotation_id)
    if quotation.status == Quotation.Status.CONVERTED:
        raise ValidationError("Cannot decline a quotation that has already been converted into a subscription.")

    quotation.status = Quotation.Status.DECLINED
    if reason:
        quotation.notes = f"{quotation.notes}\nDecline reason: {reason}".strip()
    quotation.save(update_fields=["status", "notes", "updated_at"])
    return quotation
