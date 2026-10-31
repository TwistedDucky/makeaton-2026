from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        UPI = "upi", "UPI"
        OTHER = "other", "Other"

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payments",
        help_text="Customer who made the payment.",
    )
    method = models.CharField(
        max_length=20,
        choices=Method.choices,
        default=Method.CARD,
        help_text="Payment method used.",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Total payment amount; must be strictly positive.",
    )
    payment_date = models.DateField(
        default=timezone.localdate,
        help_text="Date when payment was made.",
    )
    note = models.TextField(
        blank=True,
        default="",
        help_text="Optional remarks or notes about the payment.",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_payments",
        help_text="Staff or admin user who recorded the payment.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-payment_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal("0.00")),
                name="payment_amount_gt_0",
            )
        ]
        indexes = [
            models.Index(fields=["customer"]),
            models.Index(fields=["payment_date"]),
            models.Index(fields=["method"]),
        ]

    def __str__(self):
        return f"Payment {self.id} - {self.customer} - {self.amount} ({self.method})"

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= Decimal("0.00"):
            raise ValidationError({"amount": "Payment amount must be greater than zero."})


class PaymentAllocation(models.Model):
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="allocations",
        help_text="The payment being allocated.",
    )
    invoice = models.ForeignKey(
        "billing.Invoice",
        on_delete=models.PROTECT,
        related_name="payment_allocations",
        help_text="Invoice to which this portion of payment is allocated.",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Amount allocated to this invoice; must be strictly positive.",
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal("0.00")),
                name="payment_allocation_amount_gt_0",
            ),
            models.UniqueConstraint(
                fields=["payment", "invoice"],
                name="unique_payment_invoice_allocation",
            ),
        ]
        indexes = [
            models.Index(fields=["payment"]),
            models.Index(fields=["invoice"]),
        ]

    def __str__(self):
        return f"Allocation {self.id}: {self.amount} to {self.invoice.number}"

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= Decimal("0.00"):
            raise ValidationError({"amount": "Allocation amount must be greater than zero."})
