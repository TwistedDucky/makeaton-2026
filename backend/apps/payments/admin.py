from django.contrib import admin

from .models import Payment, PaymentAllocation


class PaymentAllocationInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 0
    fields = ["invoice", "amount"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "customer",
        "method",
        "amount",
        "payment_date",
        "recorded_by",
        "created_at",
    ]
    list_filter = ["method", "payment_date"]
    search_fields = [
        "customer__email",
        "customer__first_name",
        "customer__last_name",
        "note",
    ]
    readonly_fields = ["created_at"]
    inlines = [PaymentAllocationInline]


@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "payment",
        "invoice",
        "amount",
    ]
    search_fields = [
        "invoice__number",
        "payment__customer__email",
    ]
