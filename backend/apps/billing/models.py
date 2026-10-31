import logging
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, models, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

TWOPLACES = Decimal("0.01")


def quantize_money(amount: Decimal) -> Decimal:
    """Round a Decimal amount to 2 decimal places using standard ROUND_HALF_UP."""
    if amount is None:
        amount = Decimal("0.00")
    return amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


class IllegalStatusTransitionError(ValidationError):
    """Raised when an invalid status transition is attempted on an invoice."""
    pass


def generate_invoice_number(year: int) -> str:
    """
    Generate the next sequential invoice number in the format INV-<YYYY>-<00001>.
    Must be called within a database transaction holding an advisory lock to guarantee race safety.
    """
    prefix = f"INV-{year}-"
    last_invoice = (
        Invoice.objects.filter(number__startswith=prefix)
        .order_by("-number")
        .first()
    )
    if last_invoice and last_invoice.number:
        try:
            last_seq = int(last_invoice.number.split("-")[-1])
        except (ValueError, IndexError):
            last_seq = 0
    else:
        last_seq = 0

    next_seq = last_seq + 1
    return f"{prefix}{next_seq:05d}"


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CONFIRMED = "confirmed", "Confirmed"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(
        max_length=32,
        unique=True,
        editable=False,
        help_text="Unique auto-generated invoice reference (e.g. INV-2026-00001).",
    )
    # Plain reference for now; becomes a real FK when subscriptions models are merged.
    subscription_id = models.PositiveBigIntegerField(
        db_index=True,
        help_text="Plain reference for now; becomes a real FK when subscriptions models are merged.",
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    period_start = models.DateField(
        help_text="Start date of the subscription billing period.",
    )
    period_end = models.DateField(
        help_text="End date of the subscription billing period.",
    )
    issue_date = models.DateField(
        default=timezone.localdate,
        help_text="Date on which the invoice was issued.",
    )
    due_date = models.DateField(
        help_text="Date by which payment for this invoice is due.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    # Money fields (max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    discount_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    tax_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    amount_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription_id", "period_start"],
                condition=~models.Q(status="cancelled"),
                name="unique_subscription_period_start_active",
            ),
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=Decimal("0.00")),
                name="invoice_subtotal_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(discount_total__gte=Decimal("0.00")),
                name="invoice_discount_total_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(tax_total__gte=Decimal("0.00")),
                name="invoice_tax_total_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(total__gte=Decimal("0.00")),
                name="invoice_total_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(amount_paid__gte=Decimal("0.00")),
                name="invoice_amount_paid_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(amount_paid__lte=models.F("total")),
                name="invoice_amount_paid_lte_total",
            ),
            models.CheckConstraint(
                condition=models.Q(due_date__gte=models.F("issue_date")),
                name="invoice_due_date_gte_issue_date",
            ),
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")),
                name="invoice_period_end_gte_period_start",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "due_date"]),
            models.Index(fields=["customer", "status"]),
        ]

    def __str__(self):
        return f"{self.number or 'Draft'} - {self.customer} ({self.status})"

    def clean(self):
        super().clean()
        if self.issue_date and self.due_date and self.due_date < self.issue_date:
            raise ValidationError({"due_date": "Invoice due_date cannot precede issue_date."})
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValidationError({"period_end": "Invoice period_end cannot precede period_start."})
        if self.amount_paid is not None and self.total is not None and self.amount_paid > self.total:
            raise ValidationError({"amount_paid": "amount_paid cannot exceed total."})

    def save(self, *args, **kwargs):
        if not self.number:
            target_year = (self.issue_date or timezone.localdate()).year
            with transaction.atomic():
                if connection.vendor == "postgresql":
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_advisory_xact_lock(%s);", [target_year])
                self.number = generate_invoice_number(target_year)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    def recalculate_totals(self, save=True):
        """
        Recalculate invoice monetary totals based on all associated line items:
            subtotal = sum(quantity * unit_price)
            discount_total = sum(discount_amount)
            tax_total = sum(tax_amount)
            total = subtotal - discount_total + tax_total

        Guards: Raises ValidationError unless status == draft.
        Guaranteed: Does NOT alter invoice status or amount_paid.
        """
        if self.status != self.Status.DRAFT:
            raise ValidationError(
                f"Cannot recalculate totals on invoice {self.number or self.id}: "
                f"current status is '{self.status}', but totals can only be recalculated on '{self.Status.DRAFT}' invoices."
            )

        lines = list(self.lines.all())
        new_subtotal = Decimal("0.00")
        new_discount_total = Decimal("0.00")
        new_tax_total = Decimal("0.00")

        for line in lines:
            line_sub = (Decimal(line.quantity) * line.unit_price)
            new_subtotal += line_sub
            new_discount_total += line.discount_amount
            new_tax_total += line.tax_amount

        self.subtotal = quantize_money(new_subtotal)
        self.discount_total = quantize_money(new_discount_total)
        self.tax_total = quantize_money(new_tax_total)
        self.total = quantize_money(self.subtotal - self.discount_total + self.tax_total)

        if save and self.pk:
            self.save(update_fields=["subtotal", "discount_total", "tax_total", "total", "updated_at"])

    # Status transition methods
    def confirm(self):
        """
        Transition invoice from draft -> confirmed.
        """
        if self.status != self.Status.DRAFT:
            raise IllegalStatusTransitionError(
                f"Cannot confirm invoice {self.number or self.id}: current status is '{self.status}', "
                f"but only '{self.Status.DRAFT}' invoices can be confirmed."
            )
        self.status = self.Status.CONFIRMED
        self.save(update_fields=["status", "updated_at"])

    def mark_paid(self):
        """
        Transition invoice from confirmed -> paid.
        Guarded: requires status == confirmed AND amount_paid >= total.
        (A zero-total invoice with amount_paid 0 may be marked paid.)
        """
        if self.status != self.Status.CONFIRMED:
            raise IllegalStatusTransitionError(
                f"Cannot mark invoice {self.number or self.id} as paid: current status is '{self.status}', "
                f"but only '{self.Status.CONFIRMED}' invoices can be marked as paid."
            )
        if self.amount_paid < self.total:
            raise IllegalStatusTransitionError(
                f"Cannot mark invoice {self.number or self.id} as paid: amount_paid ({self.amount_paid}) "
                f"is less than total ({self.total}). Invoice must be fully paid."
            )
        self.status = self.Status.PAID
        self.save(update_fields=["status", "updated_at"])

    def cancel(self):
        """
        Transition invoice to cancelled from draft or confirmed only.
        Guarded: raises if amount_paid > 0 (part-paid or paid invoice cannot be cancelled silently).
        """
        if self.status not in (self.Status.DRAFT, self.Status.CONFIRMED):
            raise IllegalStatusTransitionError(
                f"Cannot cancel invoice {self.number or self.id}: current status is '{self.status}'. "
                f"Only '{self.Status.DRAFT}' or '{self.Status.CONFIRMED}' invoices can be cancelled."
            )
        if self.amount_paid > Decimal("0.00"):
            raise IllegalStatusTransitionError(
                f"Cannot cancel invoice {self.number or self.id}: invoice has recorded payments "
                f"(amount_paid = {self.amount_paid}). Part-paid or paid invoices cannot be cancelled."
            )
        self.status = self.Status.CANCELLED
        self.save(update_fields=["status", "updated_at"])


class InvoiceLine(models.Model):
    """
    Represents an individual line item on an invoice.

    Canonical Formula:
        line_subtotal = quantity * unit_price
        discounted_subtotal = line_subtotal - discount_amount
        line_total = discounted_subtotal + tax_amount

    Tax is calculated on the discounted amount (line_subtotal - discount_amount).
    All money amounts are quantized to 2 decimal places using Decimal with ROUND_HALF_UP.
    """
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    # References catalog product (becomes real FK when catalog models are merged)
    product_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Catalog product ID reference; becomes real FK when catalog is merged.",
    )
    product_name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="invoiceline_quantity_gt_0",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=Decimal("0.00")),
                name="invoiceline_unit_price_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(discount_amount__gte=Decimal("0.00")),
                name="invoiceline_discount_amount_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(tax_amount__gte=Decimal("0.00")),
                name="invoiceline_tax_amount_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(discount_amount__lte=models.F("quantity") * models.F("unit_price")),
                name="invoiceline_discount_lte_subtotal",
            ),
        ]

    def __str__(self):
        return f"{self.product_name} x {self.quantity} ({self.invoice.number})"

    def compute_line_total(self) -> Decimal:
        """
        Compute line_total using the canonical formula:
            line_subtotal = quantity * unit_price
            discounted_subtotal = line_subtotal - discount_amount
            line_total = discounted_subtotal + tax_amount
        Rounds to 2 decimal places using ROUND_HALF_UP.
        """
        qty = Decimal(self.quantity or 1)
        price = self.unit_price or Decimal("0.00")
        discount = self.discount_amount or Decimal("0.00")
        tax = self.tax_amount or Decimal("0.00")

        line_subtotal = qty * price
        discounted_subtotal = line_subtotal - discount
        calculated_total = discounted_subtotal + tax
        return quantize_money(calculated_total)

    def clean(self):
        super().clean()
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({"quantity": "Quantity must be greater than zero."})
        if self.unit_price is not None and self.unit_price < Decimal("0.00"):
            raise ValidationError({"unit_price": "unit_price cannot be negative."})
        if self.discount_amount is not None and self.discount_amount < Decimal("0.00"):
            raise ValidationError({"discount_amount": "discount_amount cannot be negative."})
        if self.tax_amount is not None and self.tax_amount < Decimal("0.00"):
            raise ValidationError({"tax_amount": "tax_amount cannot be negative."})

        # Discount must not exceed line subtotal
        if self.quantity is not None and self.unit_price is not None and self.discount_amount is not None:
            subtotal = Decimal(self.quantity) * self.unit_price
            if self.discount_amount > subtotal:
                raise ValidationError({"discount_amount": "Discount amount cannot exceed line subtotal (quantity * unit_price)."})

    def save(self, *args, **kwargs):
        # Recompute line_total on EVERY save via compute_line_total()
        self.line_total = self.compute_line_total()
        super().save(*args, **kwargs)
