from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Subscription, SubscriptionLine
from .services import (
    advance_next_billing_date,
    get_due_subscriptions,
    transition_subscription,
)
from apps.catalog.models import Plan, Product

User = get_user_model()


class SubscriptionStateMachineTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="customer@example.com",
            password="Password123!",
            role="CUSTOMER",
        )
        self.plan = Plan.objects.create(
            name="Monthly Pro",
            price=Decimal("99.00"),
            billing_period="monthly",
            available_from=date(2026, 1, 1),
            auto_close=True,
        )
        self.product = Product.objects.create(
            name="SaaS License",
            type="service",
            sales_price=Decimal("99.00"),
            cost_price=Decimal("10.00"),
        )
        self.subscription = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status=Subscription.Status.DRAFT,
            start_date=date(2026, 1, 1),
            expiry_date=date(2026, 3, 31),
        )
        self.line = SubscriptionLine.objects.create(
            subscription=self.subscription,
            product=self.product,
            quantity=2,
            unit_price=Decimal("99.00"),
            taxes=Decimal("10.00"),
        )
        self.subscription.recalculate_totals()

    def test_totals_calculation(self):
        # 2 * 99 + 10 = 208
        self.assertEqual(self.subscription.subtotal, Decimal("198.00"))
        self.assertEqual(self.subscription.tax_amount, Decimal("10.00"))
        self.assertEqual(self.subscription.total_amount, Decimal("208.00"))

    def test_valid_state_machine_flow(self):
        # Draft -> Quotation
        transition_subscription(self.subscription, Subscription.Status.QUOTATION)
        self.assertEqual(self.subscription.status, Subscription.Status.QUOTATION)

        # Quotation -> Confirmed
        transition_subscription(self.subscription, Subscription.Status.CONFIRMED)
        self.assertEqual(self.subscription.status, Subscription.Status.CONFIRMED)

        # Confirmed -> Active
        transition_subscription(self.subscription, Subscription.Status.ACTIVE)
        self.assertEqual(self.subscription.status, Subscription.Status.ACTIVE)
        self.assertIsNotNone(self.subscription.current_period_start)
        self.assertIsNotNone(self.subscription.current_period_end)
        self.assertIsNotNone(self.subscription.next_billing_date)

        # Active -> Closed
        transition_subscription(self.subscription, Subscription.Status.CLOSED, reason="Customer request")
        self.assertEqual(self.subscription.status, Subscription.Status.CLOSED)
        self.assertEqual(self.subscription.cancellation_reason, "Customer request")

    def test_invalid_transition_fails(self):
        # Draft cannot jump directly to Active
        with self.assertRaises(ValidationError):
            transition_subscription(self.subscription, Subscription.Status.ACTIVE)

    def test_closed_is_terminal(self):
        transition_subscription(self.subscription, Subscription.Status.CLOSED)
        # Cannot move out of Closed
        with self.assertRaises(ValidationError):
            transition_subscription(self.subscription, Subscription.Status.ACTIVE)

    def test_member_4_billing_integrations(self):
        # Move to Active
        transition_subscription(self.subscription, Subscription.Status.CONFIRMED)
        transition_subscription(self.subscription, Subscription.Status.ACTIVE)

        due_list = get_due_subscriptions(target_date=date(2026, 1, 15))
        self.assertEqual(len(due_list), 1)
        due_item = due_list[0]
        self.assertEqual(due_item["id"], self.subscription.id)
        self.assertEqual(due_item["customer_id"], self.customer.id)
        self.assertEqual(due_item["payment_terms_days"], 30)
        self.assertEqual(len(due_item["lines"]), 1)
        self.assertEqual(due_item["lines"][0]["unit_price"], Decimal("99.00"))

        # Test advance billing date
        result = advance_next_billing_date(self.subscription.id)
        self.subscription.refresh_from_db()
        self.assertGreater(result["next_billing_date"], date(2026, 1, 1))

    def test_renewal_extends_expiry_date(self):
        transition_subscription(self.subscription, Subscription.Status.CONFIRMED)
        transition_subscription(self.subscription, Subscription.Status.ACTIVE)
        initial_expiry = self.subscription.expiry_date

        from .services import renew_subscription
        renewed = renew_subscription(self.subscription.id)
        self.assertGreater(renewed.expiry_date, initial_expiry)

    def test_renewal_fails_if_plan_not_renewable(self):
        self.plan.renewable = False
        self.plan.save()
        transition_subscription(self.subscription, Subscription.Status.CONFIRMED)
        transition_subscription(self.subscription, Subscription.Status.ACTIVE)

        from .services import renew_subscription
        with self.assertRaises(ValidationError):
            renew_subscription(self.subscription.id)

