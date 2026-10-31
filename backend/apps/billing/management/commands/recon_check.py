"""Temporary recon script."""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone


class Command(BaseCommand):
    help = "Recon check for task 7"

    def handle(self, *args, **options):
        User = get_user_model()
        self.stdout.write("=== ROW COUNTS ===")
        self.stdout.write("Users by role:")
        for role in ['ADMIN', 'STAFF', 'CUSTOMER']:
            c = User.objects.filter(role=role).count()
            self.stdout.write(f"  {role}: {c}")

        from apps.subscriptions.models import Subscription
        self.stdout.write("Subscriptions by status:")
        for s in Subscription.Status:
            c = Subscription.objects.filter(status=s.value).count()
            self.stdout.write(f"  {s.value}: {c}")

        from apps.billing.models import Invoice
        self.stdout.write(f"Invoices total: {Invoice.objects.count()}")
        inv_by_status = {}
        for s in Invoice.Status:
            inv_by_status[s.value] = Invoice.objects.filter(status=s.value).count()
        self.stdout.write(f"  by status: {inv_by_status}")

        from apps.payments.models import Payment
        self.stdout.write(f"Payments: {Payment.objects.count()}")

        try:
            from apps.catalog.models import Discount
            self.stdout.write(f"Discounts: {Discount.objects.count()}")
        except Exception as e:
            self.stdout.write(f"Discounts error: {e}")

        try:
            from apps.billing.models import DiscountUsage
            self.stdout.write(f"DiscountUsage: {DiscountUsage.objects.count()}")
        except Exception as e:
            self.stdout.write(f"DiscountUsage error: {e}")

        from apps.subscriptions.services import get_due_subscriptions
        today = timezone.localdate()
        due = get_due_subscriptions(today)
        self.stdout.write(f"\nDue subscriptions today ({today}): {len(due)}")
        for d in due:
            self.stdout.write(f"  sub_id={d['id']}")
            self.stdout.write(f"  keys: {list(d.keys())}")
            self.stdout.write(f"  has payment_terms_days: {'payment_terms_days' in d}")

