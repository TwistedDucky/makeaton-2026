from collections.abc import Iterable
from datetime import date
from django.db.models import F, QuerySet

from .models import Discount, Product, ProductVariant, Tax


def get_active_product(product_id: int) -> Product | None:
    """Return active Product with the given ID, or None if not found."""
    return Product.objects.filter(id=product_id, is_active=True).first()


def get_active_variant(product_id: int, variant_id: int) -> ProductVariant | None:
    """Return active ProductVariant with the given ID and product_id, or None."""
    return ProductVariant.objects.filter(
        id=variant_id,
        product_id=product_id,
        is_active=True,
    ).first()


def taxes_in_bulk(ids: Iterable[int]) -> dict[int, Tax]:
    """Return dictionary mapping tax ID to Tax instance for the given IDs."""
    return Tax.objects.in_bulk(ids)


def active_discounts_on(billing_date: date) -> QuerySet[Discount]:
    """Return active Discounts valid on the given billing date with remaining usages."""
    return Discount.objects.filter(
        is_active=True,
        start_date__lte=billing_date,
        end_date__gte=billing_date,
        used_count__lt=F("usage_limit"),
    )

