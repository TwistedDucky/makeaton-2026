from rest_framework import serializers
from .models import Subscription, SubscriptionLine
from apps.catalog.models import Product, ProductVariant, Plan


class SubscriptionLineSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source="product.name")
    variant_display = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionLine
        fields = [
            "id",
            "product",
            "product_name",
            "variant",
            "variant_display",
            "quantity",
            "unit_price",
            "taxes",
            "amount",
        ]
        read_only_fields = ["amount"]

    def get_variant_display(self, obj):
        if obj.variant:
            return f"{obj.variant.attribute}: {obj.variant.value}"
        return None


class SubscriptionSerializer(serializers.ModelSerializer):
    customer_email = serializers.ReadOnlyField(source="customer.email")
    plan_name = serializers.ReadOnlyField(source="plan.name")
    plan_billing_period = serializers.ReadOnlyField(source="plan.billing_period")
    lines = SubscriptionLineSerializer(many=True, required=False)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "subscription_number",
            "customer",
            "customer_email",
            "plan",
            "plan_name",
            "plan_billing_period",
            "status",
            "start_date",
            "expiry_date",
            "payment_terms",
            "current_period_start",
            "current_period_end",
            "next_billing_date",
            "last_billed_date",
            "subtotal",
            "tax_amount",
            "total_amount",
            "quotation",
            "notes",
            "cancellation_reason",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "subscription_number",
            "subtotal",
            "tax_amount",
            "total_amount",
            "current_period_start",
            "current_period_end",
            "next_billing_date",
            "last_billed_date",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        lines_data = self.context.get("request").data.get("lines", [])
        subscription = Subscription.objects.create(**validated_data)

        for line_item in lines_data:
            SubscriptionLine.objects.create(
                subscription=subscription,
                product_id=line_item["product"],
                variant_id=line_item.get("variant"),
                quantity=line_item.get("quantity", 1),
                unit_price=line_item.get("unit_price", 0),
                taxes=line_item.get("taxes", 0),
            )

        subscription.recalculate_totals()
        return subscription


class SubscriptionTransitionSerializer(serializers.Serializer):
    target_status = serializers.ChoiceField(choices=Subscription.Status.choices)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
