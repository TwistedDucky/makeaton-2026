from django.contrib import admin

from .models import Invoice, InvoiceLine


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    fields = [
        "product_name",
        "quantity",
        "unit_price",
        "discount_amount",
        "tax_amount",
        "line_total",
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
    inlines = [InvoiceLineInline]


@admin.register(InvoiceLine)
class InvoiceLineAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "invoice",
        "product_name",
        "quantity",
        "unit_price",
        "line_total",
    ]
    search_fields = [
        "product_name",
        "invoice__number",
    ]
