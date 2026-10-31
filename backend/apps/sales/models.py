import uuid
from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def generate_quotation_number():
    date_str = timezone.now().strftime("%Y%m%d")
    short_uuid = uuid.uuid4().hex[:6].upper()
    return f"QT-{date_str}-{short_uuid}"


class QuotationTemplate(models.Model):
    name = models.CharField(max_length=200, help_text="Template name (e.g. Enterprise Yearly Starter)")
    plan = models.ForeignKey(
        "catalog.Plan",
        on_delete=models.PROTECT,
        related_name="quotation_templates",
        help_text="Default subscription plan to pre-fill.",
    )
    validity_days = models.PositiveIntegerField(
        default=30,
        help_text="Number of days this quotation remains valid once created.",
    )
    payment_terms = models.CharField(
        max_length=20,
        default="NET_30",
        help_text="Default payment terms (e.g. IMMEDIATE, NET_15, NET_30, NET_60).",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.plan.name})"


class QuotationTemplateLine(models.Model):
    template = models.ForeignKey(
        QuotationTemplate,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Leave blank to use the product's catalog sales price + variant adjustment.",
    )

    def get_unit_price(self):
        if self.unit_price is not None:
            return self.unit_price
        price = self.product.sales_price
        if self.variant and self.variant.extra_price:
            price += self.variant.extra_price
        return price

    def __str__(self):
        return f"{self.product.name} x {self.quantity} on template {self.template.name}"


class Quotation(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SENT = "SENT", "Sent"
        ACCEPTED = "ACCEPTED", "Accepted"
        DECLINED = "DECLINED", "Declined"
        EXPIRED = "EXPIRED", "Expired"
        CONVERTED = "CONVERTED", "Converted to Subscription"

    quotation_number = models.CharField(
        max_length=50,
        unique=True,
        default=generate_quotation_number,
        editable=False,
        db_index=True,
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="quotations",
    )
    sales_rep = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_quotations",
    )
    template = models.ForeignKey(
        QuotationTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotations",
    )
    plan = models.ForeignKey(
        "catalog.Plan",
        on_delete=models.PROTECT,
        related_name="quotations",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    valid_until = models.DateField()
    payment_terms = models.CharField(
        max_length=20,
        default="NET_30",
    )

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

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["status", "valid_until"]),
        ]

    def recalculate_totals(self):
        lines = self.lines.all()
        subtotal = sum((line.quantity * line.unit_price) for line in lines)
        tax_amount = sum(line.taxes for line in lines)
        self.subtotal = Decimal(str(subtotal))
        self.tax_amount = Decimal(str(tax_amount))
        self.total_amount = self.subtotal + self.tax_amount
        self.save(update_fields=["subtotal", "tax_amount", "total_amount", "updated_at"])

    def is_expired(self):
        return timezone.now().date() > self.valid_until and self.status not in [
            self.Status.ACCEPTED,
            self.Status.CONVERTED,
        ]

    def __str__(self):
        return f"{self.quotation_number} - {self.customer.email} ({self.get_status_display()})"


class QuotationLine(models.Model):
    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
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
    )

    def save(self, *args, **kwargs):
        self.amount = Decimal(str(self.quantity * self.unit_price)) + Decimal(str(self.taxes))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} x {self.quantity} for quote {self.quotation.quotation_number}"
