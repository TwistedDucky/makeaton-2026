import uuid
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def generate_subscription_number():
    date_str = timezone.now().strftime("%Y%m%d")
    short_uuid = uuid.uuid4().hex[:6].upper()
    return f"SUB-{date_str}-{short_uuid}"


class Subscription(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        QUOTATION = "QUOTATION", "Quotation"
        CONFIRMED = "CONFIRMED", "Confirmed"
        ACTIVE = "ACTIVE", "Active"
        CLOSED = "CLOSED", "Closed"

    class PaymentTerms(models.TextChoices):
        IMMEDIATE = "IMMEDIATE", "Immediate Payment"
        NET_15 = "NET_15", "Net 15 Days"
        NET_30 = "NET_30", "Net 30 Days"
        NET_60 = "NET_60", "Net 60 Days"

    # Contract identification
    subscription_number = models.CharField(
        max_length=50,
        unique=True,
        default=generate_subscription_number,
        editable=False,
        db_index=True,
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="subscriptions",
        help_text="Customer associated with this subscription.",
    )
    plan = models.ForeignKey(
        "catalog.Plan",
        on_delete=models.PROTECT,
        related_name="subscriptions",
        help_text="Plan defining the billing frequency and lifecycle rules.",
    )

    # State Machine Pipeline
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    # Contract timeline
    start_date = models.DateField(default=timezone.now)
    expiry_date = models.DateField(null=True, blank=True)
    payment_terms = models.CharField(
        max_length=20,
        choices=PaymentTerms.choices,
        default=PaymentTerms.NET_30,
    )

    # Billing tracking (for Member 4 invoice generation & renewals)
    current_period_start = models.DateField(null=True, blank=True)
    current_period_end = models.DateField(null=True, blank=True)
    next_billing_date = models.DateField(null=True, blank=True, db_index=True)
    last_billed_date = models.DateField(null=True, blank=True)

    # Financial totals
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    # Originating quotation (if converted from sales)
    quotation = models.ForeignKey(
        "sales.Quotation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="converted_subscriptions",
    )

    # Audit & notes
    notes = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "next_billing_date"]),
            models.Index(fields=["customer", "status"]),
        ]

    def clean(self):
        super().clean()
        if self.start_date and self.expiry_date:
            if self.expiry_date < self.start_date:
                raise ValidationError({"expiry_date": "Expiry date cannot be before start date."})

    def recalculate_totals(self):
        """Calculates and saves aggregate totals from all related subscription lines."""
        lines = self.lines.all()
        subtotal = sum((line.quantity * line.unit_price) for line in lines)
        tax_amount = sum(line.taxes for line in lines)
        self.subtotal = Decimal(str(subtotal))
        self.tax_amount = Decimal(str(tax_amount))
        self.total_amount = self.subtotal + self.tax_amount
        self.save(update_fields=["subtotal", "tax_amount", "total_amount", "updated_at"])

    def __str__(self):
        return f"{self.subscription_number} - {self.customer.email} ({self.get_status_display()})"


class SubscriptionLine(models.Model):
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="subscription_lines",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscription_lines",
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Unit price including any product variant adjustments.",
    )
    taxes = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Line total: (quantity * unit_price) + taxes",
    )

    def save(self, *args, **kwargs):
        self.amount = Decimal(str(self.quantity * self.unit_price)) + Decimal(str(self.taxes))
        super().save(*args, **kwargs)

    def __str__(self):
        variant_desc = f" ({self.variant.value})" if self.variant else ""
        return f"{self.product.name}{variant_desc} x {self.quantity} for {self.subscription.subscription_number}"
