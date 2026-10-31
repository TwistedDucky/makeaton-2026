import sys
import types
from apps import catalog
if not hasattr(catalog, "services"):
    catalog.services = types.ModuleType("apps.catalog.services")
    sys.modules["apps.catalog.services"] = catalog.services
from dataclasses import dataclass
import inspect
import threading
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.utils import IntegrityError
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from .models import IllegalStatusTransitionError, Invoice, InvoiceDiscount, InvoiceLine, quantize_money

User = get_user_model()


class InvoiceModelTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="customer@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )

    def _create_invoice(
        self,
        subscription_id=100,
        period_start=None,
        period_end=None,
        status=Invoice.Status.DRAFT,
        subtotal=Decimal("100.00"),
        discount_total=Decimal("0.00"),
        tax_total=Decimal("10.00"),
        total=Decimal("110.00"),
        amount_paid=Decimal("0.00"),
        issue_date=None,
        due_date=None,
    ):
        start = period_start or date(2026, 1, 1)
        end = period_end or (start + timedelta(days=30))
        iss = issue_date or start
        due = due_date or (iss + timedelta(days=15))
        return Invoice.objects.create(
            customer=self.customer,
            subscription_id=subscription_id,
            period_start=start,
            period_end=end,
            issue_date=iss,
            due_date=due,
            status=status,
            subtotal=subtotal,
            discount_total=discount_total,
            tax_total=tax_total,
            total=total,
            amount_paid=amount_paid,
        )

    # -------------------------------------------------------------------------
    # Allowed Status Transitions
    # -------------------------------------------------------------------------
    def test_allowed_transition_draft_to_confirmed(self):
        invoice = self._create_invoice(subscription_id=1, status=Invoice.Status.DRAFT)
        self.assertEqual(invoice.status, Invoice.Status.DRAFT)
        invoice.confirm()
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)

    def test_allowed_transition_confirmed_to_paid_fully_paid(self):
        invoice = self._create_invoice(
            subscription_id=2,
            status=Invoice.Status.CONFIRMED,
            total=Decimal("100.00"),
            amount_paid=Decimal("100.00"),
        )
        invoice.mark_paid()
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.PAID)

    def test_allowed_transition_confirmed_to_paid_zero_total(self):
        # A zero-total invoice with amount_paid 0 may be marked paid
        invoice = self._create_invoice(
            subscription_id=21,
            status=Invoice.Status.CONFIRMED,
            subtotal=Decimal("0.00"),
            total=Decimal("0.00"),
            amount_paid=Decimal("0.00"),
        )
        invoice.mark_paid()
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.PAID)

    def test_allowed_transition_draft_to_cancelled(self):
        invoice = self._create_invoice(subscription_id=3, status=Invoice.Status.DRAFT, amount_paid=Decimal("0.00"))
        invoice.cancel()
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CANCELLED)

    def test_allowed_transition_confirmed_to_cancelled_unpaid(self):
        invoice = self._create_invoice(subscription_id=4, status=Invoice.Status.CONFIRMED, amount_paid=Decimal("0.00"))
        invoice.cancel()
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CANCELLED)

    # -------------------------------------------------------------------------
    # Guarded mark_paid() Tests
    # -------------------------------------------------------------------------
    def test_mark_paid_blocked_if_unpaid(self):
        invoice = self._create_invoice(
            subscription_id=50,
            status=Invoice.Status.CONFIRMED,
            total=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
        )
        with self.assertRaises(IllegalStatusTransitionError) as ctx:
            invoice.mark_paid()
        self.assertIn("Invoice must be fully paid", str(ctx.exception))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)

    def test_mark_paid_blocked_if_part_paid(self):
        invoice = self._create_invoice(
            subscription_id=51,
            status=Invoice.Status.CONFIRMED,
            total=Decimal("100.00"),
            amount_paid=Decimal("50.00"),
        )
        with self.assertRaises(IllegalStatusTransitionError) as ctx:
            invoice.mark_paid()
        self.assertIn("is less than total", str(ctx.exception))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)

    def test_mark_paid_blocked_if_draft_even_if_amount_paid_equals_total(self):
        invoice = self._create_invoice(
            subscription_id=52,
            status=Invoice.Status.DRAFT,
            total=Decimal("100.00"),
            amount_paid=Decimal("100.00"),
        )
        with self.assertRaises(IllegalStatusTransitionError):
            invoice.mark_paid()
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.DRAFT)

    # -------------------------------------------------------------------------
    # Guarded cancel() Tests
    # -------------------------------------------------------------------------
    def test_cancel_blocked_if_part_paid(self):
        invoice = self._create_invoice(
            subscription_id=60,
            status=Invoice.Status.CONFIRMED,
            total=Decimal("100.00"),
            amount_paid=Decimal("40.00"),
        )
        with self.assertRaises(IllegalStatusTransitionError) as ctx:
            invoice.cancel()
        self.assertIn("invoice has recorded payments", str(ctx.exception))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)

    def test_cancel_blocked_if_already_paid(self):
        invoice = self._create_invoice(
            subscription_id=61,
            status=Invoice.Status.CONFIRMED,
            total=Decimal("100.00"),
            amount_paid=Decimal("100.00"),
        )
        invoice.mark_paid()
        with self.assertRaises(IllegalStatusTransitionError):
            invoice.cancel()
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.PAID)

    # -------------------------------------------------------------------------
    # Other Illegal Status Transitions
    # -------------------------------------------------------------------------
    def test_illegal_transition_draft_to_paid(self):
        invoice = self._create_invoice(subscription_id=5, status=Invoice.Status.DRAFT)
        with self.assertRaises(IllegalStatusTransitionError):
            invoice.mark_paid()
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.DRAFT)

    def test_illegal_transition_confirmed_to_draft(self):
        invoice = self._create_invoice(subscription_id=6, status=Invoice.Status.CONFIRMED)
        with self.assertRaises(IllegalStatusTransitionError):
            invoice.confirm()
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)

    def test_illegal_transitions_from_paid(self):
        invoice = self._create_invoice(
            subscription_id=7,
            status=Invoice.Status.CONFIRMED,
            total=Decimal("100.00"),
            amount_paid=Decimal("100.00"),
        )
        invoice.mark_paid()
        self.assertEqual(invoice.status, Invoice.Status.PAID)

        with self.assertRaises(IllegalStatusTransitionError):
            invoice.confirm()
        with self.assertRaises(IllegalStatusTransitionError):
            invoice.mark_paid()
        with self.assertRaises(IllegalStatusTransitionError):
            invoice.cancel()

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.PAID)

    def test_illegal_transitions_from_cancelled(self):
        invoice = self._create_invoice(subscription_id=8, status=Invoice.Status.DRAFT)
        invoice.cancel()
        self.assertEqual(invoice.status, Invoice.Status.CANCELLED)

        with self.assertRaises(IllegalStatusTransitionError):
            invoice.confirm()
        with self.assertRaises(IllegalStatusTransitionError):
            invoice.mark_paid()
        with self.assertRaises(IllegalStatusTransitionError):
            invoice.cancel()

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CANCELLED)

    # -------------------------------------------------------------------------
    # Database Money Integrity CheckConstraints on Invoice
    # -------------------------------------------------------------------------
    def test_db_constraint_subtotal_gte_0(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create_invoice(subscription_id=70, subtotal=Decimal("-1.00"))

    def test_db_constraint_discount_total_gte_0(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create_invoice(subscription_id=71, discount_total=Decimal("-0.01"))

    def test_db_constraint_tax_total_gte_0(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create_invoice(subscription_id=72, tax_total=Decimal("-5.00"))

    def test_db_constraint_total_gte_0(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create_invoice(subscription_id=73, total=Decimal("-10.00"))

    def test_db_constraint_amount_paid_gte_0(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create_invoice(subscription_id=74, amount_paid=Decimal("-10.00"))

    def test_db_constraint_amount_paid_lte_total(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create_invoice(subscription_id=75, total=Decimal("100.00"), amount_paid=Decimal("150.00"))

    def test_db_constraint_due_date_gte_issue_date(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create_invoice(
                    subscription_id=76,
                    issue_date=date(2026, 3, 15),
                    due_date=date(2026, 3, 10),
                )

    def test_db_constraint_period_end_gte_period_start(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create_invoice(
                    subscription_id=77,
                    period_start=date(2026, 3, 15),
                    period_end=date(2026, 3, 10),
                )

    # -------------------------------------------------------------------------
    # Database CheckConstraints on InvoiceLine
    # -------------------------------------------------------------------------
    def test_db_constraint_invoiceline_quantity_gt_0(self):
        invoice = self._create_invoice(subscription_id=80)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InvoiceLine.objects.create(
                    invoice=invoice,
                    product_name="Bad Qty",
                    quantity=0,
                    unit_price=Decimal("10.00"),
                )

    def test_db_constraint_invoiceline_unit_price_gte_0(self):
        invoice = self._create_invoice(subscription_id=81)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InvoiceLine.objects.create(
                    invoice=invoice,
                    product_name="Bad Price",
                    quantity=1,
                    unit_price=Decimal("-5.00"),
                )

    def test_db_constraint_invoiceline_discount_gte_0(self):
        invoice = self._create_invoice(subscription_id=82)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InvoiceLine.objects.create(
                    invoice=invoice,
                    product_name="Bad Disc",
                    quantity=1,
                    unit_price=Decimal("10.00"),
                    discount_amount=Decimal("-1.00"),
                )

    def test_db_constraint_invoiceline_tax_gte_0(self):
        invoice = self._create_invoice(subscription_id=83)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InvoiceLine.objects.create(
                    invoice=invoice,
                    product_name="Bad Tax",
                    quantity=1,
                    unit_price=Decimal("10.00"),
                    tax_amount=Decimal("-2.00"),
                )

    def test_db_constraint_invoiceline_discount_lte_subtotal(self):
        # Discount (15.00) exceeds line subtotal (1 * 10.00 = 10.00)
        invoice = self._create_invoice(subscription_id=84)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InvoiceLine.objects.create(
                    invoice=invoice,
                    product_name="Over-discounted Line",
                    quantity=1,
                    unit_price=Decimal("10.00"),
                    discount_amount=Decimal("15.00"),
                )

    def test_clean_validation_invoiceline_discount_lte_subtotal(self):
        invoice = self._create_invoice(subscription_id=85)
        line = InvoiceLine(
            invoice=invoice,
            product_name="Over-discounted Line",
            quantity=2,
            unit_price=Decimal("10.00"),  # subtotal = 20.00
            discount_amount=Decimal("25.00"),
        )
        with self.assertRaises(ValidationError) as ctx:
            line.clean()
        self.assertIn("discount_amount", ctx.exception.message_dict)

    # -------------------------------------------------------------------------
    # Date Defaults & Validation
    # -------------------------------------------------------------------------
    def test_invoice_issue_date_defaults_to_localdate(self):
        invoice = Invoice.objects.create(
            customer=self.customer,
            subscription_id=90,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            due_date=timezone.localdate() + timedelta(days=15),
            total=Decimal("50.00"),
        )
        self.assertEqual(invoice.issue_date, timezone.localdate())

    def test_due_date_preceding_issue_date_raises_clean_validation_error(self):
        invoice = Invoice(
            customer=self.customer,
            subscription_id=91,
            period_start=date(2026, 2, 1),
            period_end=date(2026, 2, 28),
            issue_date=date(2026, 2, 10),
            due_date=date(2026, 2, 5),
            total=Decimal("50.00"),
        )
        with self.assertRaises(ValidationError) as ctx:
            invoice.full_clean()
        self.assertIn("due_date", ctx.exception.message_dict)

    def test_period_end_preceding_period_start_raises_clean_validation_error(self):
        invoice = Invoice(
            customer=self.customer,
            subscription_id=92,
            period_start=date(2026, 2, 10),
            period_end=date(2026, 2, 5),
            issue_date=date(2026, 2, 1),
            due_date=date(2026, 3, 1),
            total=Decimal("50.00"),
        )
        with self.assertRaises(ValidationError) as ctx:
            invoice.full_clean()
        self.assertIn("period_end", ctx.exception.message_dict)

    # -------------------------------------------------------------------------
    # Conditional Unique Constraint: Cancelled invoices free their period
    # -------------------------------------------------------------------------
    def test_two_active_invoices_same_period_rejected(self):
        self._create_invoice(subscription_id=99, period_start=date(2026, 3, 1), status=Invoice.Status.DRAFT)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create_invoice(subscription_id=99, period_start=date(2026, 3, 1), status=Invoice.Status.DRAFT)

    def test_cancelled_invoice_frees_period_for_new_invoice(self):
        inv1 = self._create_invoice(
            subscription_id=99,
            period_start=date(2026, 3, 1),
            status=Invoice.Status.DRAFT,
        )
        inv1.cancel()
        self.assertEqual(inv1.status, Invoice.Status.CANCELLED)

        # Creating a new invoice for the same subscription and period_start now succeeds
        inv2 = self._create_invoice(
            subscription_id=99,
            period_start=date(2026, 3, 1),
            status=Invoice.Status.DRAFT,
        )
        self.assertNotEqual(inv1.id, inv2.id)
        self.assertEqual(inv2.status, Invoice.Status.DRAFT)

    def test_different_subscription_same_period_allowed(self):
        inv1 = self._create_invoice(subscription_id=101, period_start=date(2026, 4, 1))
        inv2 = self._create_invoice(subscription_id=102, period_start=date(2026, 4, 1))
        self.assertNotEqual(inv1.id, inv2.id)

    def test_same_subscription_different_period_allowed(self):
        inv1 = self._create_invoice(subscription_id=103, period_start=date(2026, 5, 1))
        inv2 = self._create_invoice(subscription_id=103, period_start=date(2026, 6, 1))
        self.assertNotEqual(inv1.id, inv2.id)

    # -------------------------------------------------------------------------
    # Invoice Line Formula, Rounding & Save Recomputation
    # -------------------------------------------------------------------------
    def test_invoice_line_canonical_formula_and_rounding_edge_case(self):
        """
        Canonical formula:
            line_subtotal = quantity * unit_price
            discounted_subtotal = line_subtotal - discount_amount
            line_total = discounted_subtotal + tax_amount
        Edge case: 3 items x 33.33 = 99.99 subtotal.
        10% discount: 99.99 * 0.10 = 9.999 -> 10.00 (ROUND_HALF_UP).
        Discounted subtotal: 99.99 - 10.00 = 89.99.
        10% tax on discounted subtotal: 89.99 * 0.10 = 8.999 -> 9.00 (ROUND_HALF_UP).
        line_total: 89.99 + 9.00 = 98.99.
        """
        invoice = self._create_invoice(subscription_id=300)
        line = InvoiceLine(
            invoice=invoice,
            product_id=42,
            product_name="Standard Tier Service",
            quantity=3,
            unit_price=Decimal("33.33"),
            discount_amount=Decimal("10.00"),
            tax_amount=Decimal("9.00"),
        )
        self.assertEqual(line.compute_line_total(), Decimal("98.99"))
        line.save()
        line.refresh_from_db()
        self.assertEqual(line.line_total, Decimal("98.99"))
        self.assertEqual(line.product_id, 42)

    def test_invoice_line_recomputes_line_total_on_every_save(self):
        invoice = self._create_invoice(subscription_id=301)
        line = InvoiceLine.objects.create(
            invoice=invoice,
            product_name="Editable Line",
            quantity=2,
            unit_price=Decimal("50.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
        )
        # Initially: 2 x 50.00 = 100.00
        self.assertEqual(line.line_total, Decimal("100.00"))

        # Edit quantity and save
        line.quantity = 3
        line.save()
        line.refresh_from_db()
        self.assertEqual(line.line_total, Decimal("150.00"))

        # Edit discount and save
        line.discount_amount = Decimal("20.00")
        line.save()
        line.refresh_from_db()
        self.assertEqual(line.line_total, Decimal("130.00"))

    # -------------------------------------------------------------------------
    # Invoice.recalculate_totals() Tests & Draft-Only Guard
    # -------------------------------------------------------------------------
    def test_recalculate_totals_aggregates_lines_on_draft(self):
        invoice = self._create_invoice(
            subscription_id=310,
            status=Invoice.Status.DRAFT,
            amount_paid=Decimal("0.00"),
            subtotal=Decimal("0.00"),
            discount_total=Decimal("0.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("0.00"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            product_name="Product A",
            quantity=2,
            unit_price=Decimal("50.00"),
            discount_amount=Decimal("10.00"),
            tax_amount=Decimal("9.00"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            product_name="Product B",
            quantity=1,
            unit_price=Decimal("30.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("3.00"),
        )

        invoice.recalculate_totals()
        invoice.refresh_from_db()

        self.assertEqual(invoice.subtotal, Decimal("130.00"))
        self.assertEqual(invoice.discount_total, Decimal("10.00"))
        self.assertEqual(invoice.tax_total, Decimal("12.00"))
        self.assertEqual(invoice.total, Decimal("132.00"))
        self.assertEqual(invoice.status, Invoice.Status.DRAFT)
        self.assertEqual(invoice.amount_paid, Decimal("0.00"))

    def test_recalculate_totals_raises_on_non_draft_invoice(self):
        invoice = self._create_invoice(
            subscription_id=311,
            status=Invoice.Status.DRAFT,
            total=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
        )
        invoice.confirm()
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)

        with self.assertRaises(ValidationError) as ctx:
            invoice.recalculate_totals()
        self.assertIn("totals can only be recalculated on 'draft' invoices", str(ctx.exception))


class InvoiceNumberConcurrencyTests(TransactionTestCase):
    """
    Concurrency test verifying that parallel creation across multiple threads
    produces unique, consecutive invoice numbers with zero duplicates and zero gaps
    using PostgreSQL advisory transaction locks.
    """
    reset_sequences = True

    def setUp(self):
        self.customer = User.objects.create_user(
            email="concurrent_payer@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )

    def test_concurrent_invoice_number_generation_no_duplicates_no_gaps(self):
        num_threads = 10
        barrier = threading.Barrier(num_threads)
        created_numbers = []
        errors = []
        lock = threading.Lock()

        def worker(thread_idx):
            from django.db import connection
            try:
                barrier.wait()
                invoice = Invoice.objects.create(
                    customer=self.customer,
                    subscription_id=5000 + thread_idx,
                    period_start=date(2026, 7, 1),
                    period_end=date(2026, 7, 31),
                    issue_date=date(2026, 7, 1),
                    due_date=date(2026, 8, 15),
                    total=Decimal("50.00"),
                )
                with lock:
                    created_numbers.append(invoice.number)
            except Exception as exc:
                with lock:
                    errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Encountered concurrency errors: {errors}")
        self.assertEqual(len(created_numbers), num_threads)

        seq_numbers = [int(num.split("-")[-1]) for num in created_numbers]
        sorted_seqs = sorted(seq_numbers)

        self.assertEqual(len(set(created_numbers)), num_threads)
        expected_seqs = list(range(sorted_seqs[0], sorted_seqs[0] + num_threads))
        self.assertEqual(sorted_seqs, expected_seqs, f"Expected contiguous sequence {expected_seqs}, got {sorted_seqs}")


class BillingIntegrationsTestCase(TestCase):
    """
    Unit tests for billing external service integrations and adapters.
    """

    @patch("apps.subscriptions.services.get_due_subscriptions")
    def test_get_due_subscriptions_real_wiring(self, mock_get_due):
        from apps.billing import integrations

        sample_due = [
            {
                "id": 42,
                "customer_id": 7,
                "period_start": date(2026, 3, 1),
                "period_end": date(2026, 3, 31),
                "lines": [
                    {
                        "product_id": 10,
                        "product_name": "Standard Plan",
                        "quantity": 1,
                        "unit_price": Decimal("50.00"),
                        # Note: variant_id omitted by Member 3's service
                    }
                ],
            }
        ]
        mock_get_due.return_value = sample_due

        result = integrations.get_due_subscriptions(target_date=date(2026, 3, 15))

        mock_get_due.assert_called_once_with(date(2026, 3, 15))
        self.assertEqual(len(result), 1)
        sub = result[0]
        self.assertEqual(sub["id"], 42)
        self.assertEqual(len(sub["lines"]), 1)
        # Normalization check: variant_id exists and defaults to None
        self.assertIn("variant_id", sub["lines"][0])
        self.assertIsNone(sub["lines"][0]["variant_id"])

    @patch("apps.subscriptions.services.get_due_subscriptions")
    def test_get_due_subscriptions_missing_period_dates_raises(self, mock_get_due):
        from apps.billing import integrations

        # Missing period_start
        mock_get_due.return_value = [
            {
                "id": 999,
                "customer_id": 7,
                "period_start": None,
                "period_end": date(2026, 3, 31),
                "lines": [],
            }
        ]
        with self.assertRaises(ValueError) as ctx:
            integrations.get_due_subscriptions(target_date=date(2026, 3, 15))
        self.assertIn("999", str(ctx.exception))

        # Missing period_end
        mock_get_due.return_value = [
            {
                "id": 888,
                "customer_id": 7,
                "period_start": date(2026, 3, 1),
                "period_end": None,
                "lines": [],
            }
        ]
        with self.assertRaises(ValueError) as ctx:
            integrations.get_due_subscriptions(target_date=date(2026, 3, 15))
        self.assertIn("888", str(ctx.exception))

    @patch("apps.subscriptions.services.advance_next_billing_date")
    def test_advance_next_billing_date_normalizes_status(self, mock_advance):
        from apps.billing import integrations

        mock_advance.return_value = {
            "subscription_id": 55,
            "next_billing_date": date(2026, 4, 1),
            "status": "active",  # lowercase status from service
        }
        res = integrations.advance_next_billing_date(55)

        mock_advance.assert_called_once_with(55)
        self.assertEqual(res["subscription_id"], 55)
        self.assertEqual(res["status"], "ACTIVE")

    @patch("apps.subscriptions.services.get_due_subscriptions")
    @patch("apps.subscriptions.services.advance_next_billing_date")
    def test_integrations_fallback_flag(self, mock_advance, mock_get_due):
        from apps.billing import integrations

        with patch.object(integrations, "USE_REAL_SUBSCRIPTIONS", False):
            due_subs = integrations.get_due_subscriptions()
            mock_get_due.assert_not_called()
            self.assertTrue(len(due_subs) > 0)
            self.assertEqual(due_subs[0]["id"], 101)

            adv_res = integrations.advance_next_billing_date(101)
            mock_advance.assert_not_called()
            self.assertEqual(adv_res["subscription_id"], 101)
            self.assertEqual(adv_res["status"], "ACTIVE")

    def test_real_service_signature_compatibility(self):
        from apps.subscriptions import services as sub_services

        # get_due_subscriptions must accept target_date
        sig_due = inspect.signature(sub_services.get_due_subscriptions)
        self.assertIn("target_date", sig_due.parameters)

        # advance_next_billing_date must accept subscription_id
        sig_adv = inspect.signature(sub_services.advance_next_billing_date)
        self.assertIn("subscription_id", sig_adv.parameters)

    @override_settings(DEBUG=True)
    def test_pricing_stub_warning(self):
        from apps.billing import integrations

        self.assertFalse(integrations.USE_REAL_PRICING)
        lines = [
            {
                "product_id": 1,
                "product_name": "Test Product",
                "quantity": 2,
                "unit_price": Decimal("25.00"),
            }
        ]
        result = integrations.price_invoice_lines(lines)
        self.assertIn("lines", result)
        self.assertIn("totals", result)
        self.assertEqual(result["totals"]["subtotal"], Decimal("50.00"))
        self.assertEqual(len(result["lines"]), 1)



class Task14HardeningTests(TestCase):
    """
    Tests for Task 1.4 & 1.4b:
    - New fields (variant_id, tax_id) on InvoiceLine and InvoiceDiscount model
    - Database-level constraints on InvoiceDiscount (positive amount, unique invoice+discount)
    - tax_id pass-through and variant_id default in integrations without mutating inputs
    - confirm refusal with discounts under USE_REAL_DISCOUNT_USAGE=False and success without
    - stub pricing guard under DEBUG=False
    - real pricing mapping when enabled with computed value assertions
    - redeem_discounts deduplication, stub mode, and partial failures
    """

    def setUp(self):
        self.customer = User.objects.create_user(
            email="task14_customer@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )

    def _create_invoice(self, status=Invoice.Status.DRAFT, total=Decimal("100.00")):
        return Invoice.objects.create(
            customer=self.customer,
            subscription_id=1001,
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
            issue_date=date(2026, 4, 1),
            due_date=date(2026, 5, 1),
            subtotal=total,
            discount_total=Decimal("0.00"),
            tax_total=Decimal("0.00"),
            total=total,
            amount_paid=Decimal("0.00"),
            status=status,
        )

    # -------------------------------------------------------------------------
    # 1. New Fields and InvoiceDiscount Model
    # -------------------------------------------------------------------------
    def test_invoiceline_variant_id_and_tax_id_nullable(self):
        invoice = self._create_invoice()
        line = InvoiceLine.objects.create(
            invoice=invoice,
            product_id=101,
            variant_id=202,
            tax_id=303,
            product_name="Custom Bundle",
            quantity=1,
            unit_price=Decimal("100.00"),
        )
        line.refresh_from_db()
        self.assertEqual(line.variant_id, 202)
        self.assertEqual(line.tax_id, 303)

        # Nullable check
        line_null = InvoiceLine.objects.create(
            invoice=invoice,
            product_id=102,
            variant_id=None,
            tax_id=None,
            product_name="Basic Addon",
            quantity=1,
            unit_price=Decimal("20.00"),
        )
        line_null.refresh_from_db()
        self.assertIsNone(line_null.variant_id)
        self.assertIsNone(line_null.tax_id)

    def test_invoicediscount_model_and_ordering(self):
        invoice = self._create_invoice()
        disc1 = InvoiceDiscount.objects.create(
            invoice=invoice,
            discount_id=10,
            amount=Decimal("15.00"),
        )
        disc2 = InvoiceDiscount.objects.create(
            invoice=invoice,
            discount_id=20,
            amount=Decimal("5.00"),
        )

        discounts = list(invoice.discounts.all())
        self.assertEqual(len(discounts), 2)
        self.assertEqual(discounts[0].id, disc1.id)
        self.assertEqual(discounts[1].id, disc2.id)
        self.assertIn("Discount #10", str(disc1))

    def test_invoicediscount_positive_amount_validation(self):
        invoice = self._create_invoice()
        disc_zero = InvoiceDiscount(
            invoice=invoice,
            discount_id=11,
            amount=Decimal("0.00"),
        )
        with self.assertRaises(ValidationError) as ctx:
            disc_zero.full_clean()
        self.assertIn("amount", ctx.exception.message_dict)

        disc_neg = InvoiceDiscount(
            invoice=invoice,
            discount_id=12,
            amount=Decimal("-10.00"),
        )
        with self.assertRaises(ValidationError) as ctx:
            disc_neg.full_clean()
        self.assertIn("amount", ctx.exception.message_dict)

    def test_invoicediscount_db_constraints_integrity_errors(self):
        invoice = self._create_invoice()
        # 1. amount = 0 raises IntegrityError at DB level
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InvoiceDiscount.objects.create(
                    invoice=invoice,
                    discount_id=101,
                    amount=Decimal("0.00"),
                )

        # 2. Duplicate (invoice, discount_id) raises IntegrityError
        InvoiceDiscount.objects.create(
            invoice=invoice,
            discount_id=202,
            amount=Decimal("15.00"),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InvoiceDiscount.objects.create(
                    invoice=invoice,
                    discount_id=202,
                    amount=Decimal("25.00"),
                )

    # -------------------------------------------------------------------------
    # 2. tax_id pass-through, variant_id default, and immutability of inputs
    # -------------------------------------------------------------------------
    @patch("apps.subscriptions.services.get_due_subscriptions")
    def test_tax_id_passthrough_and_variant_id_default(self, mock_get_due):
        from apps.billing import integrations

        mock_get_due.return_value = [
            {
                "id": 501,
                "customer_id": 1,
                "period_start": date(2026, 4, 1),
                "period_end": date(2026, 4, 30),
                "lines": [
                    {
                        "product_id": 1,
                        "product_name": "Tier A",
                        "variant_id": 44,
                        "quantity": 1,
                        "unit_price": Decimal("50.00"),
                        "tax_id": 99,
                    },
                    {
                        "product_id": 2,
                        "product_name": "Tier B",
                        # variant_id intentionally missing
                        "quantity": 1,
                        "unit_price": Decimal("20.00"),
                        "tax_id": None,
                    },
                ],
            }
        ]

        result = integrations.get_due_subscriptions(target_date=date(2026, 4, 15))
        self.assertEqual(len(result), 1)
        lines = result[0]["lines"]

        # Line 1: tax_id passed through untouched, variant_id preserved
        self.assertEqual(lines[0]["tax_id"], 99)
        self.assertEqual(lines[0]["variant_id"], 44)

        # Line 2: tax_id None passed through, variant_id defaulted to None
        self.assertIsNone(lines[1]["tax_id"])
        self.assertIsNone(lines[1]["variant_id"])

    @patch("apps.subscriptions.services.get_due_subscriptions")
    def test_get_due_subscriptions_normalization_does_not_mutate_inputs(self, mock_get_due):
        from apps.billing import integrations

        orig_line_1 = {
            "product_id": 1,
            "product_name": "Tier 1",
            "variant_id": 42,
            "quantity": 1,
            "unit_price": Decimal("50.00"),
            "tax_id": 7,
        }
        orig_line_2 = {
            "product_id": 2,
            "product_name": "Tier 2",
            # missing variant_id
            "quantity": 2,
            "unit_price": Decimal("25.00"),
            "tax_id": None,
        }
        orig_sub = {
            "id": 801,
            "customer_id": 12,
            "period_start": date(2026, 4, 1),
            "period_end": date(2026, 4, 30),
            "lines": [orig_line_1, orig_line_2],
        }
        mock_get_due.return_value = [orig_sub]

        result = integrations.get_due_subscriptions(target_date=date(2026, 4, 15))

        # Verify input dicts were not mutated
        self.assertNotIn("variant_id", orig_line_2, "Input line dict must not be mutated!")
        self.assertIsNot(result[0], orig_sub, "Returned sub dict must be a new dict!")
        self.assertIsNot(result[0]["lines"][0], orig_line_1, "Returned line dict must be a new dict!")
        self.assertIsNot(result[0]["lines"][1], orig_line_2, "Returned line dict must be a new dict!")

        # Verify output values
        lines = result[0]["lines"]
        self.assertEqual(lines[0]["tax_id"], 7)
        self.assertEqual(lines[0]["variant_id"], 42)
        self.assertIsNone(lines[1]["tax_id"])
        self.assertIsNone(lines[1]["variant_id"])

    # -------------------------------------------------------------------------
    # 3. Confirm refusal with discounts and success without
    # -------------------------------------------------------------------------
    def test_confirm_refuses_when_invoice_has_invoicediscount_rows_under_stub_flag(self):
        from apps.billing import integrations
        from apps.billing.services import confirm_invoice

        invoice = self._create_invoice()
        InvoiceDiscount.objects.create(
            invoice=invoice,
            discount_id=1,
            amount=Decimal("10.00"),
        )

        with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", False):
            with self.assertRaises(ValidationError) as ctx:
                invoice.confirm()
            self.assertIn("USE_REAL_DISCOUNT_USAGE is False", str(ctx.exception))
            invoice.refresh_from_db()
            self.assertEqual(invoice.status, Invoice.Status.DRAFT)

            # Confirm service helper also refuses
            with self.assertRaises(ValidationError):
                confirm_invoice(invoice)

    def test_confirm_refuses_when_invoice_has_line_discount_under_stub_flag(self):
        from apps.billing import integrations

        invoice = self._create_invoice()
        InvoiceLine.objects.create(
            invoice=invoice,
            product_name="Discounted Line",
            quantity=1,
            unit_price=Decimal("50.00"),
            discount_amount=Decimal("5.00"),
        )

        with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", False):
            with self.assertRaises(ValidationError) as ctx:
                invoice.confirm()
            self.assertIn("USE_REAL_DISCOUNT_USAGE is False", str(ctx.exception))
            invoice.refresh_from_db()
            self.assertEqual(invoice.status, Invoice.Status.DRAFT)

    def test_confirm_succeeds_when_invoice_has_zero_discounts(self):
        from apps.billing import integrations
        from apps.billing.services import confirm_invoice

        invoice = self._create_invoice()
        InvoiceLine.objects.create(
            invoice=invoice,
            product_name="Clean Line",
            quantity=1,
            unit_price=Decimal("50.00"),
            discount_amount=Decimal("0.00"),
        )

        with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", False):
            confirm_invoice(invoice)
            invoice.refresh_from_db()
            self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)

    def test_confirm_succeeds_with_discounts_when_real_discount_usage_is_true(self):
        from apps.billing import integrations

        invoice = self._create_invoice()
        InvoiceDiscount.objects.create(
            invoice=invoice,
            discount_id=1,
            amount=Decimal("10.00"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            product_name="Discounted Line",
            quantity=1,
            unit_price=Decimal("50.00"),
            discount_amount=Decimal("5.00"),
        )

        with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", True):
            invoice.confirm()
            invoice.refresh_from_db()
            self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)

    # -------------------------------------------------------------------------
    # 4. Stub guard under DEBUG=False
    # -------------------------------------------------------------------------
    @override_settings(DEBUG=False)
    def test_stub_guard_raises_under_debug_false(self):
        from apps.billing import integrations

        lines = [
            {
                "product_id": 1,
                "quantity": 1,
                "unit_price": Decimal("20.00"),
            }
        ]

        # Case 1: USE_REAL_PRICING is False
        with patch.object(integrations, "USE_REAL_PRICING", False):
            with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", True):
                with self.assertRaises(RuntimeError) as ctx:
                    integrations.price_invoice_lines(lines)
                self.assertIn("DEBUG=False", str(ctx.exception))

        # Case 2: USE_REAL_DISCOUNT_USAGE is False
        with patch.object(integrations, "USE_REAL_PRICING", True):
            with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", False):
                with self.assertRaises(RuntimeError) as ctx:
                    integrations.price_invoice_lines(lines)
                self.assertIn("DEBUG=False", str(ctx.exception))

    @override_settings(DEBUG=True)
    def test_stub_allowed_under_debug_true(self):
        from apps.billing import integrations

        lines = [
            {
                "product_id": 1,
                "quantity": 1,
                "unit_price": Decimal("20.00"),
            }
        ]
        res = integrations.price_invoice_lines(lines)
        self.assertIn("totals", res)
        self.assertEqual(res["totals"]["subtotal"], Decimal("20.00"))

    # -------------------------------------------------------------------------
    # 5. Real-pricing mapping when enabled (catalog mocked)
    # -------------------------------------------------------------------------
    def test_real_pricing_mapping_when_enabled(self):
        from apps.billing import integrations
        import sys
        from unittest.mock import MagicMock

        # Create mock objects representing catalog services
        @dataclass
        class MockLine:
            product_id: int
            quantity: int
            unit_price: Decimal
            tax_id: int | None = None
            line_discount: Decimal = Decimal("0.00")
            tax_amount: Decimal = Decimal("0.00")

            @property
            def net(self) -> Decimal:
                return max(Decimal(self.quantity) * self.unit_price - self.line_discount, Decimal("0.00"))

        @dataclass
        class MockDiscountLine:
            discount_id: int
            description: str
            amount: Decimal
            line_index: int | None

        @dataclass
        class MockPricedInvoice:
            lines: list
            discount_lines: list
            subtotal: Decimal
            discount_total: Decimal
            tax_total: Decimal
            total: Decimal

        mock_catalog_services = MagicMock()
        mock_catalog_services.Line = MockLine

        fake_priced = MockPricedInvoice(
            lines=[
                MockLine(
                    product_id=1,
                    quantity=2,
                    unit_price=Decimal("50.00"),
                    tax_id=10,
                    line_discount=Decimal("10.00"),
                    tax_amount=Decimal("9.00"),
                )
            ],
            discount_lines=[
                MockDiscountLine(
                    discount_id=5,
                    description="Spring Promo",
                    amount=Decimal("-10.00"),
                    line_index=0,
                )
            ],
            subtotal=Decimal("100.00"),
            discount_total=Decimal("10.00"),
            tax_total=Decimal("9.00"),
            total=Decimal("99.00"),
        )
        mock_catalog_services.price_invoice.return_value = fake_priced

        input_lines = [
            {
                "product_id": 1,
                "variant_id": 77,
                "product_name": "Premium Cloud Suite",
                "quantity": 2,
                "unit_price": Decimal("50.00"),
                "tax_id": 10,
            }
        ]

        with patch.dict(sys.modules, {"apps.catalog.services": mock_catalog_services}):
            with patch.object(integrations, "USE_REAL_PRICING", True):
                with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", True):
                    result = integrations.price_invoice_lines(input_lines, billing_date=date(2026, 4, 1))

        # Check call arguments constructed from input items
        mock_catalog_services.price_invoice.assert_called_once()
        call_args = mock_catalog_services.price_invoice.call_args[0]
        cat_lines, cat_date = call_args
        self.assertEqual(cat_date, date(2026, 4, 1))
        self.assertEqual(len(cat_lines), 1)
        self.assertEqual(cat_lines[0].product_id, input_lines[0]["product_id"])
        self.assertEqual(cat_lines[0].quantity, input_lines[0]["quantity"])
        self.assertEqual(cat_lines[0].unit_price, input_lines[0]["unit_price"])
        self.assertEqual(cat_lines[0].tax_id, input_lines[0]["tax_id"])

        # Check mapped return structure computed against inputs and mock catalog service
        self.assertEqual(len(result["lines"]), len(input_lines))
        mapped_line = result["lines"][0]
        cat_line = fake_priced.lines[0]
        input_item = input_lines[0]

        self.assertEqual(mapped_line["product_id"], input_item["product_id"])
        self.assertEqual(mapped_line["variant_id"], input_item["variant_id"])
        self.assertEqual(mapped_line["product_name"], input_item["product_name"])
        self.assertEqual(mapped_line["discount_amount"], cat_line.line_discount)
        self.assertEqual(mapped_line["tax_amount"], cat_line.tax_amount)
        self.assertEqual(mapped_line["tax_id"], input_item["tax_id"])
        expected_line_total = quantize_money(cat_line.net + cat_line.tax_amount)
        self.assertEqual(mapped_line["line_total"], expected_line_total)

        # Check discount_lines computed
        self.assertEqual(len(result["discount_lines"]), len(fake_priced.discount_lines))
        disc_line = result["discount_lines"][0]
        cat_disc = fake_priced.discount_lines[0]
        self.assertEqual(disc_line["discount_id"], cat_disc.discount_id)
        self.assertEqual(disc_line["description"], cat_disc.description)
        self.assertEqual(disc_line["amount"], abs(cat_disc.amount))

        # Check totals computed
        self.assertEqual(result["totals"]["subtotal"], fake_priced.subtotal)
        self.assertEqual(result["totals"]["discount_total"], fake_priced.discount_total)
        self.assertEqual(result["totals"]["tax_total"], fake_priced.tax_total)
        expected_total = quantize_money(fake_priced.subtotal - fake_priced.discount_total + fake_priced.tax_total)
        self.assertEqual(result["totals"]["total"], expected_total)

    # -------------------------------------------------------------------------
    # 6. redeem_discounts Tests
    # -------------------------------------------------------------------------
    def test_redeem_discounts_stub_mode(self):
        from apps.billing import integrations

        with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", False):
            res = integrations.redeem_discounts([1, 2, 2, 3], invoice_id=10, subscription_id=20)
            self.assertTrue(res["all_recorded"])
            self.assertEqual(res["failed_ids"], [])

    @patch("apps.catalog.services.record_discount_usage", create=True)
    def test_redeem_discounts_deduplicates_and_records(self, mock_record):
        from apps.billing import integrations

        mock_record.return_value = True

        with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", True):
            res = integrations.redeem_discounts([5, 10, 5, 20, 10], invoice_id=101, subscription_id=505)

        # Called once per distinct id: 5, 10, 20 (preserving order)
        self.assertEqual(mock_record.call_count, 3)
        mock_record.assert_any_call(5, 101, 505)
        mock_record.assert_any_call(10, 101, 505)
        mock_record.assert_any_call(20, 101, 505)
        self.assertTrue(res["all_recorded"])
        self.assertEqual(res["failed_ids"], [])

    @patch("apps.catalog.services.record_discount_usage", create=True)
    def test_redeem_discounts_partial_failure_reports_failed_ids(self, mock_record):
        from apps.billing import integrations

        def fake_record(d_id, inv_id, sub_id):
            return d_id != 10

        mock_record.side_effect = fake_record

        with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", True):
            res = integrations.redeem_discounts([5, 10, 20], invoice_id=102, subscription_id=506)

        self.assertFalse(res["all_recorded"])
        self.assertEqual(res["failed_ids"], [10])
