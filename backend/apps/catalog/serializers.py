from copy import copy
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Discount, DiscountUsage, Plan, Product, ProductVariant, Tax


class ModelCleanValidateMixin:
    """
    Mixin that builds a copy of the instance updated with incoming values,
    calls model clean(), and converts Django ValidationError into DRF ValidationError.
    """

    def validate(self, attrs):
        attrs = super().validate(attrs)

        model_cls = getattr(getattr(self, "Meta", None), "model", None)
        if model_cls is not None:
            if self.instance is not None:
                instance = copy(self.instance)
                for attr, value in attrs.items():
                    setattr(instance, attr, value)
            else:
                instance = model_cls(**attrs)

            try:
                instance.clean()
            except DjangoValidationError as exc:
                if hasattr(exc, "message_dict"):
                    raise serializers.ValidationError(exc.message_dict)
                if hasattr(exc, "messages"):
                    raise serializers.ValidationError(exc.messages)
                raise serializers.ValidationError(str(exc))

        return attrs


class TaxSerializer(ModelCleanValidateMixin, serializers.ModelSerializer):
    class Meta:
        model = Tax
        fields = [
            "id",
            "name",
            "kind",
            "rate",
            "is_active",
        ]


class ProductVariantSerializer(ModelCleanValidateMixin, serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product",
            "attribute",
            "value",
            "extra_price",
            "is_active",
        ]


class ProductSerializer(ModelCleanValidateMixin, serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "type",
            "sales_price",
            "cost_price",
            "notes",
            "tax",
            "is_active",
            "variants",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request and getattr(request, "user", None):
            if getattr(request.user, "role", None) == "CUSTOMER":
                data.pop("cost_price", None)
                data.pop("notes", None)
        return data


class PlanSerializer(ModelCleanValidateMixin, serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "id",
            "name",
            "price",
            "billing_period",
            "min_quantity",
            "available_from",
            "available_to",
            "auto_close",
            "closable",
            "pausable",
            "renewable",
            "is_active",
        ]


class DiscountSerializer(ModelCleanValidateMixin, serializers.ModelSerializer):
    class Meta:
        model = Discount
        fields = [
            "id",
            "name",
            "kind",
            "value",
            "min_purchase",
            "min_quantity",
            "start_date",
            "end_date",
            "usage_limit",
            "used_count",
            "scope",
            "product",
            "is_active",
        ]
        read_only_fields = ["used_count"]


class DiscountUsageSerializer(ModelCleanValidateMixin, serializers.ModelSerializer):
    class Meta:
        model = DiscountUsage
        fields = [
            "id",
            "discount",
            "invoice_id",
            "subscription_id",
            "created_at",
        ]
        read_only_fields = ["created_at"]

