from collections.abc import Iterable
from datetime import date
from django.db.models import F, QuerySet

from .models import Discount, DiscountUsage, Plan, Product, ProductVariant, Tax


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


def visible_products(user) -> QuerySet[Product]:
    """
    Return products visible to the user with prefetched variants.
    ADMIN and STAFF see all products; CUSTOMER only sees active products.
    """
    qs = Product.objects.prefetch_related("variants")
    if (
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "role", None) in ["ADMIN", "STAFF"]
    ):
        return qs
    return qs.filter(is_active=True)


def visible_variants(product: Product, user) -> QuerySet[ProductVariant]:
    """
    Return product variants visible to the user.
    ADMIN and STAFF see all variants; CUSTOMER only sees active variants.
    """
    qs = product.variants.all()
    if (
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "role", None) in ["ADMIN", "STAFF"]
    ):
        return qs
    return qs.filter(is_active=True)


def visible_plans(user) -> QuerySet[Plan]:
    """
    Return plans visible to the user.
    ADMIN and STAFF see all plans; CUSTOMER only sees active plans.
    """
    qs = Plan.objects.all()
    if (
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "role", None) in ["ADMIN", "STAFF"]
    ):
        return qs
    return qs.filter(is_active=True)


def all_taxes() -> QuerySet[Tax]:
    """Return all tax records."""
    return Tax.objects.all()


def all_discounts() -> QuerySet[Discount]:
    """Return all discount records with product preloaded."""
    return Discount.objects.select_related("product").all()


def discount_usages(discount: Discount) -> QuerySet[DiscountUsage]:
    """Return all usage records for a discount ordered newest first."""
    return DiscountUsage.objects.filter(discount=discount).order_by("-created_at")
