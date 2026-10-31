from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import (
    Quotation,
    QuotationLine,
    QuotationTemplate,
    QuotationTemplateLine,
)
from .services import (
    accept_quotation,
    create_quotation_from_template,
    send_quotation,
)
from apps.catalog.models import Plan, Product
from apps.subscriptions.models import Subscription
from apps.subscriptions.services import convert_quotation_to_subscription

User = get_user_model()


class QuotationWorkflowTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="lead@example.com",
            password="Password123!",
            role="CUSTOMER",
        )
        self.sales_rep = User.objects.create_user(
            email="rep@example.com",
            password="Password123!",
            role="STAFF",
        )
        self.plan = Plan.objects.create(
            name="Enterprise Annual",
            price=Decimal("1200.00"),
            billing_period="yearly",
            available_from=date(2026, 1, 1),
        )
        self.product = Product.objects.create(
            name="CRM Module",
            type="software",
            sales_price=Decimal("500.00"),
            cost_price=Decimal("50.00"),
        )
        self.template = QuotationTemplate.objects.create(
            name="Enterprise Bundle",
            plan=self.plan,
            validity_days=15,
            payment_terms="NET_30",
        )
        QuotationTemplateLine.objects.create(
            template=self.template,
            product=self.product,
            quantity=3,
        )

    def test_create_from_template(self):
        quote = create_quotation_from_template(
            template_id=self.template.id,
            customer_id=self.customer.id,
            sales_rep_id=self.sales_rep.id,
        )
        self.assertEqual(quote.customer, self.customer)
        self.assertEqual(quote.sales_rep, self.sales_rep)
        self.assertEqual(quote.status, Quotation.Status.DRAFT)
        self.assertEqual(quote.lines.count(), 1)
        self.assertEqual(quote.subtotal, Decimal("1500.00"))  # 3 * 500

    def test_accept_and_convert_to_subscription(self):
        quote = create_quotation_from_template(
            template_id=self.template.id,
            customer_id=self.customer.id,
            sales_rep_id=self.sales_rep.id,
        )
        send_quotation(quote.id)
        accept_quotation(quote.id)
        quote.refresh_from_db()
        self.assertEqual(quote.status, Quotation.Status.ACCEPTED)

        # Convert to subscription
        subscription = convert_quotation_to_subscription(quote.id)
        self.assertIsInstance(subscription, Subscription)
        self.assertEqual(subscription.customer, self.customer)
        self.assertEqual(subscription.plan, self.plan)
        self.assertEqual(subscription.status, Subscription.Status.CONFIRMED)
        self.assertEqual(subscription.lines.count(), 1)
        self.assertEqual(subscription.total_amount, Decimal("1500.00"))

        quote.refresh_from_db()
        self.assertEqual(quote.status, Quotation.Status.CONVERTED)
