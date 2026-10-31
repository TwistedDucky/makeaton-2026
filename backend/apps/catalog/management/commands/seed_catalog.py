from datetime import date, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Discount, Plan, Product, ProductVariant, Tax


class Command(BaseCommand):
    help = "Seed catalog data (taxes, products, variants, plans, discounts) idempotently."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding catalog data...")

        created_counts = {
            "taxes": 0,
            "products": 0,
            "variants": 0,
            "plans": 0,
            "discounts": 0,
        }

        # 1. Taxes
        taxes_data = [
            {"name": "GST 18%", "kind": Tax.Kind.PERCENT, "rate": Decimal("18.00")},
            {"name": "GST 5%", "kind": Tax.Kind.PERCENT, "rate": Decimal("5.00")},
        ]
        taxes_by_name = {}
        for item in taxes_data:
            tax, created = Tax.objects.get_or_create(
                name=item["name"],
                defaults={
                    "kind": item["kind"],
                    "rate": item["rate"],
                    "is_active": True,
                },
            )
            taxes_by_name[item["name"]] = tax
            if created:
                created_counts["taxes"] += 1
                self.stdout.write(f"  + Created Tax: {tax.name}")

        tax_18 = taxes_by_name["GST 18%"]
        tax_5 = taxes_by_name["GST 5%"]

        # 2. Products
        products_data = [
            {
                "name": "Brightloop CRM",
                "type": "software",
                "sales_price": Decimal("2000.00"),
                "cost_price": Decimal("800.00"),
                "notes": "Comprehensive customer relationship management suite.",
                "tax": tax_18,
            },
            {
                "name": "Brightloop ERP",
                "type": "software",
                "sales_price": Decimal("5000.00"),
                "cost_price": Decimal("2000.00"),
                "notes": "Enterprise resource planning and financial management.",
                "tax": tax_18,
            },
            {
                "name": "Priority Support add-on",
                "type": "service",
                "sales_price": Decimal("500.00"),
                "cost_price": Decimal("150.00"),
                "notes": "24/7 dedicated support and accelerated SLA.",
                "tax": tax_5,
            },
        ]
        products_by_name = {}
        for item in products_data:
            product, created = Product.objects.get_or_create(
                name=item["name"],
                defaults={
                    "type": item["type"],
                    "sales_price": item["sales_price"],
                    "cost_price": item["cost_price"],
                    "notes": item["notes"],
                    "tax": item["tax"],
                    "is_active": True,
                },
            )
            products_by_name[item["name"]] = product
            if created:
                created_counts["products"] += 1
                self.stdout.write(f"  + Created Product: {product.name}")

        crm_product = products_by_name["Brightloop CRM"]
        erp_product = products_by_name["Brightloop ERP"]

        # 3. Variants
        variants_data = [
            {
                "product": crm_product,
                "attribute": "Brand",
                "value": "Odoo",
                "extra_price": Decimal("560.00"),
            },
            {
                "product": crm_product,
                "attribute": "Brand",
                "value": "Zoho",
                "extra_price": Decimal("300.00"),
            },
            {
                "product": erp_product,
                "attribute": "Edition",
                "value": "Enterprise",
                "extra_price": Decimal("1500.00"),
            },
        ]
        for item in variants_data:
            variant, created = ProductVariant.objects.get_or_create(
                product=item["product"],
                attribute=item["attribute"],
                value=item["value"],
                defaults={
                    "extra_price": item["extra_price"],
                    "is_active": True,
                },
            )
            if created:
                created_counts["variants"] += 1
                self.stdout.write(
                    f"  + Created Variant: {variant.product.name} ({variant.attribute}={variant.value})"
                )

        # 4. Plans
        yesterday = date.today() - timedelta(days=1)
        plans_data = [
            {
                "name": "Monthly Starter",
                "price": Decimal("1999.00"),
                "billing_period": Plan.BillingPeriod.MONTHLY,
                "closable": True,
                "renewable": True,
                "pausable": False,
                "auto_close": False,
            },
            {
                "name": "Pro Growth",
                "price": Decimal("4999.00"),
                "billing_period": Plan.BillingPeriod.MONTHLY,
                "pausable": True,
                "closable": True,
                "renewable": True,
                "auto_close": False,
            },
            {
                "name": "Enterprise Annual",
                "price": Decimal("49999.00"),
                "billing_period": Plan.BillingPeriod.YEARLY,
                "auto_close": True,
                "closable": False,
                "pausable": False,
                "renewable": True,
            },
            {
                "name": "Weekly Trial",
                "price": Decimal("499.00"),
                "billing_period": Plan.BillingPeriod.WEEKLY,
                "auto_close": True,
                "closable": True,
                "renewable": False,
                "pausable": False,
            },
        ]
        for item in plans_data:
            plan, created = Plan.objects.get_or_create(
                name=item["name"],
                defaults={
                    "price": item["price"],
                    "billing_period": item["billing_period"],
                    "closable": item["closable"],
                    "renewable": item["renewable"],
                    "pausable": item["pausable"],
                    "auto_close": item["auto_close"],
                    "min_quantity": 1,
                    "available_from": yesterday,
                    "is_active": True,
                },
            )
            if created:
                created_counts["plans"] += 1
                self.stdout.write(f"  + Created Plan: {plan.name}")

        # 5. Discounts (valid from yesterday for about 6 months)
        start_date = yesterday
        end_date = date.today() + timedelta(days=180)
        discounts_data = [
            {
                "name": "Welcome 10%",
                "kind": Discount.Kind.PERCENT,
                "value": Decimal("10.00"),
                "scope": Discount.Scope.SUBSCRIPTION,
                "usage_limit": 100,
                "min_purchase": Decimal("0.00"),
                "min_quantity": 1,
                "product": None,
            },
            {
                "name": "Volume 500 off fixed",
                "kind": Discount.Kind.FIXED,
                "value": Decimal("500.00"),
                "scope": Discount.Scope.SUBSCRIPTION,
                "usage_limit": 100,
                "min_purchase": Decimal("5000.00"),
                "min_quantity": 5,
                "product": None,
            },
            {
                "name": "CRM 15%",
                "kind": Discount.Kind.PERCENT,
                "value": Decimal("15.00"),
                "scope": Discount.Scope.PRODUCT,
                "product": crm_product,
                "usage_limit": 100,
                "min_purchase": Decimal("0.00"),
                "min_quantity": 1,
            },
        ]
        for item in discounts_data:
            discount, created = Discount.objects.get_or_create(
                name=item["name"],
                defaults={
                    "kind": item["kind"],
                    "value": item["value"],
                    "scope": item["scope"],
                    "usage_limit": item["usage_limit"],
                    "used_count": 0,
                    "min_purchase": item["min_purchase"],
                    "min_quantity": item["min_quantity"],
                    "product": item.get("product"),
                    "start_date": start_date,
                    "end_date": end_date,
                    "is_active": True,
                },
            )
            if created:
                created_counts["discounts"] += 1
                self.stdout.write(f"  + Created Discount: {discount.name}")

        total_created = sum(created_counts.values())
        if total_created == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "All catalog data already seeded. Created 0 new items."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Seeding complete. Created: "
                    f"{created_counts['taxes']} taxes, "
                    f"{created_counts['products']} products, "
                    f"{created_counts['variants']} variants, "
                    f"{created_counts['plans']} plans, "
                    f"{created_counts['discounts']} discounts."
                )
            )

