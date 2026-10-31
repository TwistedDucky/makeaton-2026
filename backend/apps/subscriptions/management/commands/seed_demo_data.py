from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Discount, Plan, Product, ProductVariant, Tax
from apps.sales.models import (
    Quotation,
    QuotationLine,
    QuotationTemplate,
    QuotationTemplateLine,
)
from apps.subscriptions.models import Subscription, SubscriptionLine
from apps.subscriptions.services import transition_subscription


class Command(BaseCommand):
    help = "Seeds comprehensive demo data for testing the Subscriptions, Quotations, and Billing platform."

    def add_arguments(self, parser):
        parser.add_argument(
            "--scale",
            type=int,
            default=0,
            help="Number of subscriptions to seed for performance/page-load testing (e.g. 2500)",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding demo data..."))

        # 1. USERS
        admin_user, _ = User.objects.get_or_create(
            email="admin@example.com",
            defaults={
                "first_name": "Admin",
                "last_name": "User",
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        admin_user.set_password("Admin123!")
        admin_user.save()

        sales_rep, _ = User.objects.get_or_create(
            email="sales@example.com",
            defaults={
                "first_name": "Sarah",
                "last_name": "Sales",
                "role": User.Role.STAFF,
                "is_staff": True,
            },
        )
        sales_rep.set_password("Staff123!")
        sales_rep.save()

        customer1, _ = User.objects.get_or_create(
            email="acme@corp.com",
            defaults={
                "first_name": "Alice",
                "last_name": "Acme",
                "role": User.Role.CUSTOMER,
                "phone_number": "+919876543210",
            },
        )
        customer1.set_password("Customer123!")
        customer1.save()

        customer2, _ = User.objects.get_or_create(
            email="stark@industries.com",
            defaults={
                "first_name": "Tony",
                "last_name": "Stark",
                "role": User.Role.CUSTOMER,
                "phone_number": "+919876543211",
            },
        )
        customer2.set_password("Customer123!")
        customer2.save()

        self.stdout.write("✓ Users created (admin@example.com, sales@example.com, acme@corp.com, stark@industries.com)")

        # 2. TAXES
        tax_gst, _ = Tax.objects.get_or_create(
            name="GST 18%",
            defaults={"kind": Tax.Kind.PERCENT, "rate": Decimal("18.00")},
        )
        tax_vat, _ = Tax.objects.get_or_create(
            name="Standard VAT 10%",
            defaults={"kind": Tax.Kind.PERCENT, "rate": Decimal("10.00")},
        )

        # 3. PRODUCTS & VARIANTS
        p_crm, _ = Product.objects.get_or_create(
            name="Cloud CRM Enterprise License",
            defaults={
                "type": "software",
                "sales_price": Decimal("120.00"),
                "cost_price": Decimal("20.00"),
                "tax": tax_gst,
                "notes": "Core per-seat enterprise access license.",
            },
        )
        v_cloud, _ = ProductVariant.objects.get_or_create(
            product=p_crm,
            attribute="Deployment",
            value="Multi-Tenant Cloud",
            defaults={"extra_price": Decimal("0.00")},
        )
        v_vpc, _ = ProductVariant.objects.get_or_create(
            product=p_crm,
            attribute="Deployment",
            value="Dedicated Private VPC",
            defaults={"extra_price": Decimal("560.00")},
        )

        p_support, _ = Product.objects.get_or_create(
            name="24/7 Dedicated SLA Support",
            defaults={
                "type": "service",
                "sales_price": Decimal("85.00"),
                "cost_price": Decimal("15.00"),
                "tax": tax_gst,
                "notes": "1-hour critical response time guarantee.",
            },
        )

        p_storage, _ = Product.objects.get_or_create(
            name="500GB High-Performance Storage",
            defaults={
                "type": "addon",
                "sales_price": Decimal("30.00"),
                "cost_price": Decimal("5.00"),
                "tax": tax_vat,
                "notes": "Encrypted NVMe storage add-on.",
            },
        )

        self.stdout.write("✓ Products & Variants created")

        # 4. PLANS
        plan_monthly, _ = Plan.objects.get_or_create(
            name="Monthly Business Pro",
            defaults={
                "price": Decimal("120.00"),
                "billing_period": Plan.BillingPeriod.MONTHLY,
                "min_quantity": 1,
                "available_from": date(2026, 1, 1),
                "auto_close": False,
                "renewable": True,
            },
        )
        plan_annual, _ = Plan.objects.get_or_create(
            name="Enterprise Annual Suite",
            defaults={
                "price": Decimal("1200.00"),
                "billing_period": Plan.BillingPeriod.YEARLY,
                "min_quantity": 5,
                "available_from": date(2026, 1, 1),
                "auto_close": True,
                "renewable": True,
            },
        )

        self.stdout.write("✓ Plans created")

        # 5. QUOTATION TEMPLATES
        tmpl_enterprise, _ = QuotationTemplate.objects.get_or_create(
            name="Enterprise SaaS Starter Bundle",
            defaults={
                "plan": plan_annual,
                "validity_days": 30,
                "payment_terms": "NET_30",
                "description": "Recommended starting package for companies with 5+ seats.",
            },
        )
        QuotationTemplateLine.objects.get_or_create(
            template=tmpl_enterprise,
            product=p_crm,
            variant=v_vpc,
            defaults={"quantity": 5, "unit_price": Decimal("680.00")},
        )
        QuotationTemplateLine.objects.get_or_create(
            template=tmpl_enterprise,
            product=p_support,
            defaults={"quantity": 1, "unit_price": Decimal("85.00")},
        )

        tmpl_pro, _ = QuotationTemplate.objects.get_or_create(
            name="Monthly Business Core",
            defaults={
                "plan": plan_monthly,
                "validity_days": 14,
                "payment_terms": "NET_15",
                "description": "Standard monthly subscription for small-medium teams.",
            },
        )
        QuotationTemplateLine.objects.get_or_create(
            template=tmpl_pro,
            product=p_crm,
            variant=v_cloud,
            defaults={"quantity": 2, "unit_price": Decimal("120.00")},
        )

        self.stdout.write("✓ Quotation Templates created")

        # 6. QUOTATIONS
        q1, _ = Quotation.objects.get_or_create(
            customer=customer1,
            plan=plan_annual,
            template=tmpl_enterprise,
            defaults={
                "sales_rep": sales_rep,
                "valid_until": timezone.now().date() + timedelta(days=25),
                "status": Quotation.Status.SENT,
                "notes": "Includes complimentary migration assistance.",
            },
        )
        QuotationLine.objects.get_or_create(
            quotation=q1,
            product=p_crm,
            variant=v_vpc,
            defaults={"quantity": 5, "unit_price": Decimal("680.00"), "taxes": Decimal("612.00")},
        )
        QuotationLine.objects.get_or_create(
            quotation=q1,
            product=p_support,
            defaults={"quantity": 1, "unit_price": Decimal("85.00"), "taxes": Decimal("15.30")},
        )
        q1.recalculate_totals()

        q2, _ = Quotation.objects.get_or_create(
            customer=customer2,
            plan=plan_monthly,
            template=tmpl_pro,
            defaults={
                "sales_rep": sales_rep,
                "valid_until": timezone.now().date() + timedelta(days=12),
                "status": Quotation.Status.DRAFT,
                "notes": "Custom quote draft awaiting sales manager review.",
            },
        )
        QuotationLine.objects.get_or_create(
            quotation=q2,
            product=p_crm,
            variant=v_cloud,
            defaults={"quantity": 3, "unit_price": Decimal("120.00"), "taxes": Decimal("64.80")},
        )
        q2.recalculate_totals()

        self.stdout.write("✓ Sample Quotations created")

        # 7. SUBSCRIPTIONS ACROSS LIFECYCLE PIPELINE
        # A. Draft
        sub_draft, _ = Subscription.objects.get_or_create(
            customer=customer2,
            plan=plan_monthly,
            status=Subscription.Status.DRAFT,
            defaults={
                "start_date": timezone.now().date(),
                "payment_terms": "NET_15",
                "notes": "Initial draft contract pending review.",
            },
        )
        SubscriptionLine.objects.get_or_create(
            subscription=sub_draft,
            product=p_crm,
            defaults={"quantity": 2, "unit_price": Decimal("120.00"), "taxes": Decimal("43.20")},
        )
        sub_draft.recalculate_totals()

        # B. Confirmed
        sub_confirmed, _ = Subscription.objects.get_or_create(
            customer=customer1,
            plan=plan_monthly,
            status=Subscription.Status.CONFIRMED,
            defaults={
                "start_date": timezone.now().date(),
                "payment_terms": "NET_30",
                "notes": "Contract signed and approved. Ready to be activated.",
            },
        )
        SubscriptionLine.objects.get_or_create(
            subscription=sub_confirmed,
            product=p_crm,
            variant=v_cloud,
            defaults={"quantity": 4, "unit_price": Decimal("120.00"), "taxes": Decimal("86.40")},
        )
        sub_confirmed.recalculate_totals()

        # C. Active (Due for billing - Ready for Member 4 demo!)
        sub_active, _ = Subscription.objects.get_or_create(
            customer=customer1,
            plan=plan_annual,
            status=Subscription.Status.ACTIVE,
            defaults={
                "start_date": timezone.now().date() - timedelta(days=30),
                "expiry_date": timezone.now().date() + timedelta(days=335),
                "current_period_start": timezone.now().date() - timedelta(days=30),
                "current_period_end": timezone.now().date(),
                "next_billing_date": timezone.now().date(),
                "payment_terms": "NET_30",
                "notes": "Live enterprise subscription. Currently due for renewal invoicing.",
            },
        )
        SubscriptionLine.objects.get_or_create(
            subscription=sub_active,
            product=p_crm,
            variant=v_vpc,
            defaults={"quantity": 5, "unit_price": Decimal("680.00"), "taxes": Decimal("612.00")},
        )
        SubscriptionLine.objects.get_or_create(
            subscription=sub_active,
            product=p_storage,
            defaults={"quantity": 3, "unit_price": Decimal("30.00"), "taxes": Decimal("9.00")},
        )
        sub_active.recalculate_totals()

        # D. Closed
        sub_closed, _ = Subscription.objects.get_or_create(
            customer=customer2,
            plan=plan_monthly,
            status=Subscription.Status.CLOSED,
            defaults={
                "start_date": timezone.now().date() - timedelta(days=120),
                "expiry_date": timezone.now().date() - timedelta(days=30),
                "cancellation_reason": "Customer migrated project to alternate division.",
                "notes": "Archived contract.",
            },
        )
        SubscriptionLine.objects.get_or_create(
            subscription=sub_closed,
            product=p_crm,
            defaults={"quantity": 1, "unit_price": Decimal("120.00"), "taxes": Decimal("21.60")},
        )
        sub_closed.recalculate_totals()

        self.stdout.write(self.style.SUCCESS("✓ Core demo data successfully seeded!"))

        scale_count = options.get("scale") or 0
        if scale_count > 0:
            self.stdout.write(self.style.NOTICE(f"Generating {scale_count} scale subscriptions for 2-second page-load benchmark..."))
            import time
            start_time = time.time()

            existing_scale = Subscription.objects.filter(subscription_number__startswith="SUB-SCALE-").count()
            start_idx = existing_scale + 1
            end_idx = start_idx + scale_count

            subs_to_create = []
            today = timezone.now().date()
            plans_pool = [plan_monthly, plan_annual]
            customers_pool = [customer1, customer2]
            statuses_pool = [
                Subscription.Status.ACTIVE,
                Subscription.Status.ACTIVE,
                Subscription.Status.ACTIVE,
                Subscription.Status.CONFIRMED,
                Subscription.Status.QUOTATION,
                Subscription.Status.CLOSED,
            ]

            for i in range(start_idx, end_idx):
                plan = plans_pool[i % len(plans_pool)]
                customer = customers_pool[i % len(customers_pool)]
                status = statuses_pool[i % len(statuses_pool)]
                start_d = today - timedelta(days=(i % 60))
                expiry_d = start_d + timedelta(days=365) if plan == plan_annual else None
                next_bill = today + timedelta(days=((i % 30) - 10)) if status == Subscription.Status.ACTIVE else None

                sub = Subscription(
                    subscription_number=f"SUB-SCALE-{i:06d}",
                    customer=customer,
                    plan=plan,
                    status=status,
                    start_date=start_d,
                    expiry_date=expiry_d,
                    payment_terms=Subscription.PaymentTerms.NET_30,
                    current_period_start=start_d,
                    current_period_end=start_d + timedelta(days=30),
                    next_billing_date=next_bill,
                    subtotal=Decimal("2000.00"),
                    tax_amount=Decimal("360.00"),
                    total_amount=Decimal("2360.00"),
                    notes=f"Scale benchmark subscription #{i}",
                )
                subs_to_create.append(sub)

            created_subs = Subscription.objects.bulk_create(subs_to_create, batch_size=1000)

            lines_to_create = []
            for sub in created_subs:
                lines_to_create.append(
                    SubscriptionLine(
                        subscription=sub,
                        product=p_crm,
                        variant=v_cloud,
                        quantity=1,
                        unit_price=Decimal("2000.00"),
                        taxes=Decimal("360.00"),
                        amount=Decimal("2360.00"),
                    )
                )

            SubscriptionLine.objects.bulk_create(lines_to_create, batch_size=1000)
            elapsed = time.time() - start_time
            total_subs = Subscription.objects.count()
            total_lines = SubscriptionLine.objects.count()

            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Successfully seeded {scale_count} scale subscriptions ({len(lines_to_create)} lines) in {elapsed:.2f}s! Total in DB: {total_subs} subscriptions, {total_lines} lines."
                )
            )

        self.stdout.write(self.style.SUCCESS("""
Credentials for testing:
- Admin:    admin@example.com / Admin123!
- Sales:    sales@example.com / Staff123!
- Customer: acme@corp.com     / Customer123!
- Customer: stark@industries.com / Customer123!
"""))
