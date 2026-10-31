"""Catalog pricing and discount calculation services.

Note for the billing app:
All functions in this module are read-only and never mutate database records
or increment Discount.used_count. When an invoice is finalized or paid, the
billing app must increment discount usage inside its own transaction.atomic() using:

    updated = Discount.objects.filter(
        pk=id,
        used_count__lt=F("usage_limit"),
    ).update(used_count=F("used_count") + 1)

and skip the discount if 0 rows were updated.
"""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .models import Discount, Tax
from .selectors import (
    active_discounts_on,
    get_active_product,
    get_active_variant,
    taxes_in_bulk,
)

TWOPLACES = Decimal("0.01")


def money(x) -> Decimal:
    """Return Decimal rounded to 0.01 using ROUND_HALF_UP."""
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Line:
    product_id: int
    quantity: int
    unit_price: Decimal
    tax_id: int | None = None
    line_discount: Decimal = Decimal("0.00")
    tax_amount: Decimal = Decimal("0.00")

    def __post_init__(self):
        object.__setattr__(self, "unit_price", money(self.unit_price))
        object.__setattr__(self, "line_discount", money(self.line_discount))
        object.__setattr__(self, "tax_amount", money(self.tax_amount))

    @property
    def gross(self) -> Decimal:
        return money(Decimal(self.quantity) * self.unit_price)

    @property
    def net(self) -> Decimal:
        return max(self.gross - self.line_discount, Decimal("0.00"))


@dataclass(frozen=True)
class DiscountLine:
    discount_id: int
    description: str
    amount: Decimal  # negative
    line_index: int | None = None

    def __post_init__(self):
        val = money(self.amount)
        if val > Decimal("0.00"):
            val = -val
        object.__setattr__(self, "amount", val)


@dataclass(frozen=True)
class PricedInvoice:
    lines: list[Line]
    discount_lines: list[DiscountLine]
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    total: Decimal


def get_line_price(product_id: int, variant_id: int | None = None) -> Decimal:
    """Return product sales_price + variant extra_price."""
    product = get_active_product(product_id)
    if not product:
        raise ValueError(f"Active product with id {product_id} not found.")

    price = product.sales_price
    if variant_id is not None:
        variant = get_active_variant(product_id, variant_id)
        if not variant:
            raise ValueError(
                f"Active variant with id {variant_id} for product {product_id} not found."
            )
        price += variant.extra_price

    return money(price)


def calculate_tax(lines: list[Line]) -> tuple[list[Line], Decimal]:
    """
    Calculate tax for lines using a single bulk query for taxes.
    Percent tax = net * rate / 100; fixed tax = flat amount per line.
    Skip inactive taxes and lines with net 0.
    Returns (lines_with_tax_amount, total_tax).
    """
    if not lines:
        return [], Decimal("0.00")

    tax_ids = {line.tax_id for line in lines if line.tax_id is not None}
    taxes = taxes_in_bulk(tax_ids) if tax_ids else {}

    updated_lines: list[Line] = []
    for line in lines:
        tax_amount = Decimal("0.00")
        if line.net > Decimal("0.00") and line.tax_id is not None:
            tax = taxes.get(line.tax_id)
            if tax and tax.is_active:
                if tax.kind == Tax.Kind.PERCENT:
                    tax_amount = money(line.net * tax.rate / Decimal("100"))
                elif tax.kind == Tax.Kind.FIXED:
                    tax_amount = money(tax.rate)

        updated_lines.append(replace(line, tax_amount=tax_amount))

    total_tax = money(
        sum((line.tax_amount for line in updated_lines), Decimal("0.00"))
    )
    return updated_lines, total_tax


def apply_discounts(lines: list[Line], billing_date: date) -> list[DiscountLine]:
    """
    Determine eligible discounts and return list of DiscountLine.
    Product scope: applies to lines with same product_id; pick single best discount per line.
    Subscription scope: pick single best discount on remaining subtotal after product discounts.
    """
    if not lines:
        return []

    active_discounts = list(active_discounts_on(billing_date))
    if not active_discounts:
        return []

    def compute_discount_value(discount: Discount, base: Decimal) -> Decimal:
        if discount.kind == Discount.Kind.PERCENT:
            amt = money(base * discount.value / Decimal("100"))
        else:
            amt = money(discount.value)
        return max(Decimal("0.00"), min(amt, base))

    discount_lines: list[DiscountLine] = []
    product_discount_by_line: dict[int, Decimal] = {}

    # 1. Product-scope discounts
    product_discounts = [
        d for d in active_discounts if d.scope == Discount.Scope.PRODUCT
    ]

    for idx, line in enumerate(lines):
        base = line.gross
        qty = line.quantity

        best_discount: Discount | None = None
        best_amount = Decimal("0.00")

        for d in product_discounts:
            if d.product_id != line.product_id:
                continue
            if base < d.min_purchase:
                continue
            if qty < d.min_quantity:
                continue

            amt = compute_discount_value(d, base)
            if amt > best_amount:
                best_amount = amt
                best_discount = d

        if best_discount and best_amount > Decimal("0.00"):
            product_discount_by_line[idx] = best_amount
            discount_lines.append(
                DiscountLine(
                    discount_id=best_discount.id,
                    description=best_discount.name,
                    amount=-best_amount,
                    line_index=idx,
                )
            )

    # 2. Subscription-scope discount
    subscription_discounts = [
        d for d in active_discounts if d.scope == Discount.Scope.SUBSCRIPTION
    ]

    total_gross = money(sum((line.gross for line in lines), Decimal("0.00")))
    total_prod_discounts = money(
        sum(product_discount_by_line.values(), Decimal("0.00"))
    )
    remaining_subtotal = max(Decimal("0.00"), total_gross - total_prod_discounts)
    total_quantity = sum(line.quantity for line in lines)

    best_sub_discount: Discount | None = None
    best_sub_amount = Decimal("0.00")

    for d in subscription_discounts:
        if remaining_subtotal < d.min_purchase:
            continue
        if total_quantity < d.min_quantity:
            continue

        amt = compute_discount_value(d, remaining_subtotal)
        if amt > best_sub_amount:
            best_sub_amount = amt
            best_sub_discount = d

    if best_sub_discount and best_sub_amount > Decimal("0.00"):
        discount_lines.append(
            DiscountLine(
                discount_id=best_sub_discount.id,
                description=best_sub_discount.name,
                amount=-best_sub_amount,
                line_index=None,
            )
        )

    return discount_lines


def price_invoice(lines: list[Line], billing_date: date) -> PricedInvoice:
    """
    Price an invoice with lines and billing date.
    Order:
      1. apply_discounts
      2. add product-scope discounts to each line's line_discount
      3. spread subscription-scope discount across lines in proportion to net
         (last line takes rounding remainder)
      4. calculate_tax on discounted lines
    total = subtotal - discount_total + tax_total
    """
    if not lines:
        return PricedInvoice(
            lines=[],
            discount_lines=[],
            subtotal=Decimal("0.00"),
            discount_total=Decimal("0.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("0.00"),
        )

    # 1. apply_discounts
    discount_lines = apply_discounts(lines, billing_date)

    # 2. add product-scope discounts to each line's line_discount
    prod_discounts_by_index: dict[int, Decimal] = {}
    sub_discount_line: DiscountLine | None = None

    for dl in discount_lines:
        if dl.line_index is not None:
            prod_discounts_by_index[dl.line_index] = abs(dl.amount)
        else:
            sub_discount_line = dl

    lines_after_product_discount: list[Line] = []
    for idx, line in enumerate(lines):
        p_disc = prod_discounts_by_index.get(idx, Decimal("0.00"))
        new_line_discount = money(line.line_discount + p_disc)
        lines_after_product_discount.append(
            replace(line, line_discount=new_line_discount)
        )

    # 3. spread any subscription-scope discount across lines in proportion to each line's net
    # (the last line takes the rounding remainder)
    discounted_lines: list[Line] = []
    if sub_discount_line and sub_discount_line.amount != Decimal("0.00"):
        sub_discount_amount = abs(sub_discount_line.amount)
        eligible_indices = [
            i
            for i, line in enumerate(lines_after_product_discount)
            if line.net > Decimal("0.00")
        ]
        total_net = sum(
            (lines_after_product_discount[i].net for i in eligible_indices),
            Decimal("0.00"),
        )

        sub_shares: dict[int, Decimal] = {}
        if total_net > Decimal("0.00") and eligible_indices:
            allocated = Decimal("0.00")
            for idx in eligible_indices[:-1]:
                share = money(
                    sub_discount_amount
                    * lines_after_product_discount[idx].net
                    / total_net
                )
                sub_shares[idx] = share
                allocated += share
            # The last line takes the rounding remainder
            last_idx = eligible_indices[-1]
            sub_shares[last_idx] = sub_discount_amount - allocated

        for idx, line in enumerate(lines_after_product_discount):
            add_disc = sub_shares.get(idx, Decimal("0.00"))
            new_line_discount = money(line.line_discount + add_disc)
            discounted_lines.append(replace(line, line_discount=new_line_discount))
    else:
        discounted_lines = lines_after_product_discount

    # 4. calculate_tax on the discounted lines
    lines_with_tax, tax_total = calculate_tax(discounted_lines)

    # 5. subtotal, discount_total, total
    subtotal = money(sum((line.gross for line in lines), Decimal("0.00")))
    discount_total = money(
        sum((abs(dl.amount) for dl in discount_lines), Decimal("0.00"))
    )
    total = money(subtotal - discount_total + tax_total)

    return PricedInvoice(
        lines=lines_with_tax,
        discount_lines=discount_lines,
        subtotal=subtotal,
        discount_total=discount_total,
        tax_total=tax_total,
        total=total,
    )

