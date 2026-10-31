from rest_framework import serializers
from .models import (
    QuotationTemplate,
    QuotationTemplateLine,
    Quotation,
    QuotationLine,
)


class QuotationTemplateLineSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source="product.name")
    variant_display = serializers.SerializerMethodField()

    class Meta:
        model = QuotationTemplateLine
        fields = [
            "id",
            "product",
            "product_name",
            "variant",
            "variant_display",
            "quantity",
            "unit_price",
        ]

    def get_variant_display(self, obj):
        if obj.variant:
            return f"{obj.variant.attribute}: {obj.variant.value}"
        return None


class QuotationTemplateSerializer(serializers.ModelSerializer):
    plan_name = serializers.ReadOnlyField(source="plan.name")
    lines = QuotationTemplateLineSerializer(many=True, required=False)

    class Meta:
        model = QuotationTemplate
        fields = [
            "id",
            "name",
            "plan",
            "plan_name",
            "validity_days",
            "payment_terms",
            "description",
            "is_active",
            "lines",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        template = QuotationTemplate.objects.create(**validated_data)
        for line_data in lines_data:
            QuotationTemplateLine.objects.create(template=template, **line_data)
        return template


class QuotationLineSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source="product.name")
    variant_display = serializers.SerializerMethodField()

    class Meta:
        model = QuotationLine
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


class QuotationSerializer(serializers.ModelSerializer):
    customer_email = serializers.ReadOnlyField(source="customer.email")
    sales_rep_email = serializers.ReadOnlyField(source="sales_rep.email")
    plan_name = serializers.ReadOnlyField(source="plan.name")
    template_name = serializers.ReadOnlyField(source="template.name")
    lines = QuotationLineSerializer(many=True, required=False)

    class Meta:
        model = Quotation
        fields = [
            "id",
            "quotation_number",
            "customer",
            "customer_email",
            "sales_rep",
            "sales_rep_email",
            "template",
            "template_name",
            "plan",
            "plan_name",
            "status",
            "valid_until",
            "payment_terms",
            "subtotal",
            "tax_amount",
            "total_amount",
            "notes",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "quotation_number",
            "subtotal",
            "tax_amount",
            "total_amount",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        quotation = Quotation.objects.create(**validated_data)
        for line_data in lines_data:
            QuotationLine.objects.create(quotation=quotation, **line_data)
        quotation.recalculate_totals()
        return quotation


class CreateFromTemplateSerializer(serializers.Serializer):
    template_id = serializers.IntegerField()
    customer_id = serializers.IntegerField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
