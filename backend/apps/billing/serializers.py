"""
Serializers for the billing app (invoices, lines, discounts).
"""
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .models import Invoice, InvoiceDiscount, InvoiceLine


class InvoiceCustomerSerializer(serializers.Serializer):
    """Nested representation of the invoice customer."""

    id = serializers.IntegerField(read_only=True)
    email = serializers.CharField(read_only=True)


class InvoiceLineSerializer(serializers.ModelSerializer):
    """Serializer for individual invoice line items."""

    unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True
    )
    discount_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True
    )
    tax_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True
    )
    line_total = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True
    )

    class Meta:
        model = InvoiceLine
        fields = [
            "id",
            "product_id",
            "variant_id",
            "tax_id",
            "product_name",
            "quantity",
            "unit_price",
            "discount_amount",
            "tax_amount",
            "line_total",
        ]


class InvoiceDiscountSerializer(serializers.ModelSerializer):
    """Serializer for discounts recorded against an invoice."""

    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True
    )

    class Meta:
        model = InvoiceDiscount
        fields = ["id", "discount_id", "amount"]


class InvoiceListSerializer(serializers.ModelSerializer):
    """
    Serializer for invoice list view.
    Includes computed outstanding and is_overdue flags from loaded fields without extra queries.
    """

    customer = InvoiceCustomerSerializer(read_only=True)
    subtotal = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True
    )
    discount_total = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True
    )
    tax_total = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True
    )
    total = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True
    )
    amount_paid = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True
    )
    outstanding = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            "id",
            "number",
            "subscription_id",
            "customer",
            "period_start",
            "period_end",
            "issue_date",
            "due_date",
            "status",
            "subtotal",
            "discount_total",
            "tax_total",
            "total",
            "amount_paid",
            "outstanding",
            "is_overdue",
            "created_at",
        ]

    def get_outstanding(self, obj: Invoice) -> str:
        """
        outstanding = (total - amount_paid) as a 2-decimal string ONLY when
        status == 'confirmed', else '0.00' (draft, paid, cancelled all '0.00').
        """
        if obj.status == Invoice.Status.CONFIRMED:
            rem = max(Decimal("0.00"), obj.total - obj.amount_paid)
            return f"{rem:.2f}"
        return "0.00"

    def get_is_overdue(self, obj: Invoice) -> bool:
        """
        is_overdue = status == 'confirmed' and due_date < timezone.localdate() and outstanding > 0.
        Due today is NOT overdue.
        """
        if obj.status != Invoice.Status.CONFIRMED:
            return False
        today = timezone.localdate()
        if obj.due_date >= today:
            return False
        return (obj.total - obj.amount_paid) > Decimal("0.00")


class InvoiceDetailSerializer(InvoiceListSerializer):
    """
    Serializer for invoice detail view.
    Adds nested lines and discounts.
    """

    lines = InvoiceLineSerializer(many=True, read_only=True)
    discounts = InvoiceDiscountSerializer(many=True, read_only=True)

    class Meta(InvoiceListSerializer.Meta):
        fields = InvoiceListSerializer.Meta.fields + ["lines", "discounts"]


class GenerateInvoicesInputSerializer(serializers.Serializer):
    """Optional payload for invoice generation action."""

    target_date = serializers.DateField(required=False, format="%Y-%m-%d")
