from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models


class Tax(models.Model):
    class Kind(models.TextChoices):
        PERCENT = "percent", "Percent"
        FIXED = "fixed", "Fixed"

    name = models.CharField(max_length=100, unique=True)
    kind = models.CharField(
        max_length=10,
        choices=Kind.choices,
        default=Kind.PERCENT,
    )
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def clean(self):
        super().clean()
        if self.kind == self.Kind.PERCENT:
            if self.rate is not None and (self.rate < 0 or self.rate > 100):
                raise ValidationError({"rate": "Percent rate must be between 0 and 100."})

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=50)
    sales_price = models.DecimalField(max_digits=12, decimal_places=2)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)
    tax = models.ForeignKey(
        Tax,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="products",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "name"]),
        ]

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    attribute = models.CharField(max_length=50)
    value = models.CharField(max_length=50)
    extra_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "attribute", "value"],
                name="uniq_variant_per_product",
            ),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.attribute}: {self.value}"


class Plan(models.Model):
    class BillingPeriod(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"

    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    billing_period = models.CharField(
        max_length=10,
        choices=BillingPeriod.choices,
    )
    min_quantity = models.PositiveIntegerField(default=1)
    available_from = models.DateField()
    available_to = models.DateField(null=True, blank=True)
    auto_close = models.BooleanField(default=False)
    closable = models.BooleanField(default=True)
    pausable = models.BooleanField(default=False)
    renewable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "available_from", "available_to"]),
        ]

    def clean(self):
        super().clean()
        if self.min_quantity is not None and self.min_quantity < 1:
            raise ValidationError({"min_quantity": "Minimum quantity must be at least 1."})
        if self.available_from and self.available_to:
            if self.available_to < self.available_from:
                raise ValidationError({"available_to": "Available to date must be on or after available from date."})

    def __str__(self):
        return self.name


class Discount(models.Model):
    class Kind(models.TextChoices):
        FIXED = "fixed", "Fixed"
        PERCENT = "percent", "Percent"

    class Scope(models.TextChoices):
        PRODUCT = "product", "Product"
        SUBSCRIPTION = "subscription", "Subscription"

    name = models.CharField(max_length=200)
    kind = models.CharField(
        max_length=10,
        choices=Kind.choices,
    )
    value = models.DecimalField(max_digits=12, decimal_places=2)
    min_purchase = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    min_quantity = models.PositiveIntegerField(default=1)
    start_date = models.DateField()
    end_date = models.DateField()
    usage_limit = models.PositiveIntegerField()
    used_count = models.PositiveIntegerField(default=0)
    scope = models.CharField(
        max_length=20,
        choices=Scope.choices,
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="discounts",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "start_date", "end_date"]),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.start_date and self.end_date and self.end_date <= self.start_date:
            errors["end_date"] = "End date must be after start date."

        if self.min_quantity is not None and self.min_quantity < 1:
            errors["min_quantity"] = "Minimum quantity must be at least 1."

        if self.usage_limit is not None and self.usage_limit < 1:
            errors["usage_limit"] = "Usage limit must be at least 1."

        if self.value is not None:
            if self.kind == self.Kind.PERCENT:
                if self.value <= 0 or self.value > 100:
                    errors["value"] = "Percent discount value must be in (0, 100]."
            elif self.kind == self.Kind.FIXED:
                if self.value <= 0:
                    errors["value"] = "Fixed discount value must be greater than 0."

        if self.scope == self.Scope.PRODUCT and not self.product:
            errors["product"] = "Product is required when scope is product."

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name


class DiscountUsage(models.Model):
    discount = models.ForeignKey(
        Discount,
        on_delete=models.PROTECT,
        related_name="usages",
    )
    invoice_id = models.BigIntegerField()
    subscription_id = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["discount", "invoice_id"],
                name="uniq_discount_invoice",
            ),
        ]

    def __str__(self):
        return f"Discount {self.discount_id} used on Invoice {self.invoice_id}"
