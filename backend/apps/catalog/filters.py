from django.db import models
from django.utils import timezone
from django_filters import rest_framework as filters

from .models import Discount, Plan, Product, Tax


class ProductFilter(filters.FilterSet):
    type = filters.CharFilter(field_name="type", lookup_expr="exact")
    is_active = filters.BooleanFilter(field_name="is_active")

    class Meta:
        model = Product
        fields = ["type", "is_active"]


class PlanFilter(filters.FilterSet):
    billing_period = filters.ChoiceFilter(choices=Plan.BillingPeriod.choices)
    is_active = filters.BooleanFilter(field_name="is_active")
    available = filters.BooleanFilter(method="filter_available")

    class Meta:
        model = Plan
        fields = ["billing_period", "is_active", "available"]

    def filter_available(self, queryset, name, value):
        if value is None:
            return queryset
        today = timezone.localdate()
        available_condition = models.Q(
            is_active=True,
            available_from__lte=today,
        ) & (
            models.Q(available_to__isnull=True)
            | models.Q(available_to__gte=today)
        )
        if value:
            return queryset.filter(available_condition)
        return queryset.filter(~available_condition)


class TaxFilter(filters.FilterSet):
    is_active = filters.BooleanFilter(field_name="is_active")

    class Meta:
        model = Tax
        fields = ["is_active"]


class DiscountFilter(filters.FilterSet):
    scope = filters.ChoiceFilter(choices=Discount.Scope.choices)
    is_active = filters.BooleanFilter(field_name="is_active")
    valid_on = filters.DateFilter(method="filter_valid_on")

    class Meta:
        model = Discount
        fields = ["scope", "is_active", "valid_on"]

    def filter_valid_on(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(start_date__lte=value, end_date__gte=value)

