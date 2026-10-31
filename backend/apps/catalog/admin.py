from django.contrib import admin
from .models import Discount, DiscountUsage, Plan, Product, ProductVariant, Tax


@admin.register(Tax)
class TaxAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "rate", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "sales_price", "cost_price", "tax", "is_active")
    list_filter = ("type", "is_active")
    search_fields = ("name",)


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("product", "attribute", "value", "extra_price", "is_active")
    list_filter = ("is_active", "attribute")
    search_fields = ("product__name", "attribute", "value")


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "price",
        "billing_period",
        "min_quantity",
        "available_from",
        "available_to",
        "is_active",
    )
    list_filter = ("billing_period", "is_active")
    search_fields = ("name",)


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "kind",
        "value",
        "scope",
        "product",
        "start_date",
        "end_date",
        "usage_limit",
        "used_count",
        "is_active",
    )
    list_filter = ("kind", "scope", "is_active")
    search_fields = ("name",)


@admin.register(DiscountUsage)
class DiscountUsageAdmin(admin.ModelAdmin):
    list_display = ("discount", "invoice_id", "subscription_id", "created_at")
    list_filter = ("created_at",)
    search_fields = ("discount__name", "invoice_id", "subscription_id")
