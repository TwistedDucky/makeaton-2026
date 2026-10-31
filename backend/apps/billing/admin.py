from django.contrib import admin

from .models import Invoice, InvoiceDiscount, InvoiceLine


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    fields = [
        "product_name",
        "product_id",
        "variant_id",
        "tax_id",
        "quantity",
        "unit_price",
        "discount_amount",
        "tax_amount",
        "line_total",
    ]


class InvoiceDiscountInline(admin.TabularInline):
    model = InvoiceDiscount
    extra = 0
    fields = [
        "discount_id",
        "amount",
    ]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        "number",
        "customer",
        "subscription_id",
        "status",
        "total",
        "amount_paid",
        "issue_date",
        "due_date",
    ]
    list_filter = ["status", "issue_date", "due_date"]
    search_fields = [
        "number",
        "customer__email",
        "customer__first_name",
        "customer__last_name",
        "subscription_id",
    ]
    readonly_fields = [
        "number",
        "created_at",
        "updated_at",
    ]
    inlines = [InvoiceLineInline, InvoiceDiscountInline]


@admin.register(InvoiceLine)
class InvoiceLineAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "invoice",
        "product_name",
        "product_id",
        "variant_id",
        "tax_id",
        "quantity",
        "unit_price",
        "discount_amount",
        "tax_amount",
        "line_total",
    ]
    list_filter = ["invoice__status"]
    search_fields = ["product_name", "invoice__number"]


@admin.register(InvoiceDiscount)
class InvoiceDiscountAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "invoice",
        "discount_id",
        "amount",
    ]
    list_filter = ["invoice__status"]
    search_fields = ["invoice__number", "discount_id"]
