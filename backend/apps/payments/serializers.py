"""
Serializers for payments and payment allocations.
"""
from rest_framework import serializers

from .models import Payment, PaymentAllocation


class PaymentUserSerializer(serializers.Serializer):
    """Minimal representation of a user (customer or recorded_by)."""

    id = serializers.IntegerField(read_only=True)
    email = serializers.CharField(read_only=True)


class PaymentAllocationSerializer(serializers.ModelSerializer):
    """Serializer for payment allocations to invoices."""

    invoice_id = serializers.IntegerField(source="invoice.id", read_only=True)
    invoice_number = serializers.CharField(
        source="invoice.number", read_only=True, allow_null=True
    )
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True
    )

    class Meta:
        model = PaymentAllocation
        fields = ["id", "invoice_id", "invoice_number", "amount"]


class PaymentSerializer(serializers.ModelSerializer):
    """
    Serializer for Payment list and detail views.
    Includes customer and recorded_by objects and nested allocations.
    All monetary amounts are formatted as 2-decimal strings.
    """

    customer = PaymentUserSerializer(read_only=True)
    recorded_by = PaymentUserSerializer(read_only=True)
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True
    )
    allocations = PaymentAllocationSerializer(many=True, read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "customer",
            "method",
            "amount",
            "payment_date",
            "note",
            "recorded_by",
            "created_at",
            "allocations",
        ]


class StrictStringMoneyField(serializers.Field):
    """
    Field that strictly requires incoming data to be a JSON string.
    Rejects JSON numbers (floats/ints), booleans, and nulls.
    """

    def to_internal_value(self, data):
        if not isinstance(data, str) or isinstance(data, bool):
            raise serializers.ValidationError("must be a string.")
        return data

    def to_representation(self, value):
        return str(value)


class AllocationInputSerializer(serializers.Serializer):
    """Input serializer for a single allocation item."""

    invoice = serializers.JSONField(required=True)
    amount = StrictStringMoneyField(required=True)


class PaymentCreateInputSerializer(serializers.Serializer):
    """
    Input serializer for POST /api/payments/.
    Validates field presence and types before passing to services.record_payment.
    """

    customer = serializers.IntegerField(required=True)
    method = serializers.ChoiceField(choices=Payment.Method.choices, required=True)
    amount = StrictStringMoneyField(required=True)
    payment_date = serializers.DateField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    allocations = AllocationInputSerializer(many=True, required=True, allow_empty=False)

    def validate_customer(self, value):
        raw = self.initial_data.get("customer")
        if isinstance(raw, bool) or isinstance(raw, float):
            raise serializers.ValidationError("Customer must be an integer user ID.")
        return value
