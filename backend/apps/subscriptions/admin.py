from django.contrib import admin
from .models import Subscription, SubscriptionLine


class SubscriptionLineInline(admin.TabularInline):
    model = SubscriptionLine
    extra = 1
    fields = ("product", "variant", "quantity", "unit_price", "taxes", "amount")
    readonly_fields = ("amount",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "subscription_number",
        "customer",
        "plan",
        "status",
        "start_date",
        "expiry_date",
        "next_billing_date",
        "total_amount",
    )
    list_filter = ("status", "payment_terms", "plan")
    search_fields = ("subscription_number", "customer__email", "notes")
    readonly_fields = (
        "subscription_number",
        "subtotal",
        "tax_amount",
        "total_amount",
        "created_at",
        "updated_at",
    )
    inlines = [SubscriptionLineInline]
