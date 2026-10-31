from django.contrib import admin
from .models import (
    QuotationTemplate,
    QuotationTemplateLine,
    Quotation,
    QuotationLine,
)


class QuotationTemplateLineInline(admin.TabularInline):
    model = QuotationTemplateLine
    extra = 1
    fields = ("product", "variant", "quantity", "unit_price")


@admin.register(QuotationTemplate)
class QuotationTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "plan", "validity_days", "payment_terms", "is_active")
    list_filter = ("is_active", "plan")
    search_fields = ("name", "description")
    inlines = [QuotationTemplateLineInline]


class QuotationLineInline(admin.TabularInline):
    model = QuotationLine
    extra = 1
    fields = ("product", "variant", "quantity", "unit_price", "taxes", "amount")
    readonly_fields = ("amount",)


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = (
        "quotation_number",
        "customer",
        "plan",
        "status",
        "valid_until",
        "total_amount",
    )
    list_filter = ("status", "plan", "template")
    search_fields = ("quotation_number", "customer__email")
    readonly_fields = (
        "quotation_number",
        "subtotal",
        "tax_amount",
        "total_amount",
        "created_at",
        "updated_at",
    )
    inlines = [QuotationLineInline]
