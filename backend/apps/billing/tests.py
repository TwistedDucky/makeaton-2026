from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
import inspect
import sys
import threading
from unittest.mock import MagicMock, call, patch

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

        self.assertTrue(integrations.USE_REAL_PRICING)
        lines = [
            {
                "product_id": 1,
                "product_name": "Test Product",
                "quantity": 2,
                "unit_price": Decimal("25.00"),
            }
        ]
        with patch.object(integrations, "USE_REAL_PRICING", False):
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
        with patch.object(integrations, "USE_REAL_PRICING", False):
            res = integrations.price_invoice_lines(lines)
            self.assertIn("totals", res)
            self.assertEqual(res["totals"]["subtotal"], Decimal("20.00"))

    # -------------------------------------------------------------------------
    # 5. Real pricing tests with real catalog rows (Task 1.5)
    # -------------------------------------------------------------------------
    def test_real_pricing_with_catalog_rows(self):
        from apps.billing import integrations
        from apps.catalog.models import Discount, Product, ProductVariant, Tax

        today = timezone.localdate()
        tax = Tax.objects.create(
            name="VAT 10% Real Pricing",
            kind=Tax.Kind.PERCENT,
            rate=Decimal("10.00"),
            is_active=True,
        )
        product = Product.objects.create(
            name="Cloud Storage Pro",
            type="service",
            sales_price=Decimal("200.00"),  # catalog price differs from invoice line unit_price
            cost_price=Decimal("50.00"),
            tax=tax,
            is_active=True,
        )
        variant = ProductVariant.objects.create(
            product=product,
            attribute="capacity",
            value="100GB",
            extra_price=Decimal("20.00"),
            is_active=True,
        )

        # 10% product-scope discount
        prod_disc = Discount.objects.create(
            name="10% Off Storage",
            kind=Discount.Kind.PERCENT,
            value=Decimal("10.00"),
            min_purchase=Decimal("0.00"),
            min_quantity=1,
            start_date=today - timedelta(days=10),
            end_date=today + timedelta(days=30),
            usage_limit=100,
            scope=Discount.Scope.PRODUCT,
            product=product,
            is_active=True,
        )

        # $5 subscription-scope discount
        sub_disc = Discount.objects.create(
            name="$5 Off Sub",
            kind=Discount.Kind.FIXED,
            value=Decimal("5.00"),
            min_purchase=Decimal("0.00"),
            min_quantity=1,
            start_date=today - timedelta(days=10),
            end_date=today + timedelta(days=30),
            usage_limit=100,
            scope=Discount.Scope.SUBSCRIPTION,
            is_active=True,
        )

        input_lines = [
            {
                "product_id": product.id,
                "variant_id": variant.id,
                "product_name": "Cloud Storage Pro - 100GB",
                "quantity": 1,
                "unit_price": Decimal("100.00"),  # stored frozen unit price differs from 200.00
                "tax_id": tax.id,
            }
        ]

        with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", True):
            result = integrations.price_invoice_lines(input_lines, billing_date=today)

        # Independent manual calculation:
        # Gross = 1 * 100.00 = 100.00
        # Product discount (10%) = 10.00 -> Net after prod discount = 90.00
        # Subscription discount ($5 fixed) = 5.00
        # Total line discount = 15.00 -> Net after all discounts = 85.00
        # Tax (10% on 85.00) = 8.50
        # Line total = 85.00 + 8.50 = 93.50
        exp_qty = 1
        exp_unit_price = Decimal("100.00")
        exp_discount = Decimal("15.00")
        exp_tax = Decimal("8.50")
        exp_line_total = Decimal("93.50")

        self.assertEqual(len(result["lines"]), 1)
        line = result["lines"][0]
        self.assertEqual(line["product_id"], product.id)
        self.assertEqual(line["variant_id"], variant.id)
        self.assertEqual(line["product_name"], "Cloud Storage Pro - 100GB")
        self.assertEqual(line["unit_price"], exp_unit_price)
        self.assertEqual(line["discount_amount"], exp_discount)
        self.assertEqual(line["tax_amount"], exp_tax)
        self.assertEqual(line["tax_id"], tax.id)
        self.assertEqual(line["line_total"], exp_line_total)

        # Assert line_total == qty * unit_price - discount + tax
        self.assertEqual(
            line["line_total"],
            exp_qty * exp_unit_price - exp_discount + exp_tax,
        )

        # Totals match
        totals = result["totals"]
        self.assertEqual(totals["subtotal"], Decimal("100.00"))
        self.assertEqual(totals["discount_total"], Decimal("15.00"))
        self.assertEqual(totals["tax_total"], Decimal("8.50"))
        self.assertEqual(totals["total"], Decimal("93.50"))
        self.assertEqual(
            sum(l["discount_amount"] for l in result["lines"]),
            totals["discount_total"],
        )

    def test_real_pricing_two_lines_same_product_discount_aggregation(self):
        from apps.billing import integrations
        from apps.catalog.models import Discount, Product, Tax

        today = timezone.localdate()
        tax = Tax.objects.create(
            name="VAT 10% Two Lines Agg",
            kind=Tax.Kind.PERCENT,
            rate=Decimal("10.00"),
            is_active=True,
        )
        product = Product.objects.create(
            name="Widget Single Agg",
            type="service",
            sales_price=Decimal("100.00"),
            cost_price=Decimal("40.00"),
            tax=tax,
            is_active=True,
        )
        prod_disc = Discount.objects.create(
            name="10% Off Widget Single Agg",
            kind=Discount.Kind.PERCENT,
            value=Decimal("10.00"),
            min_purchase=Decimal("0.00"),
            min_quantity=1,
            start_date=today - timedelta(days=5),
            end_date=today + timedelta(days=20),
            usage_limit=100,
            scope=Discount.Scope.PRODUCT,
            product=product,
            is_active=True,
        )

        input_lines = [
            {
                "product_id": product.id,
                "product_name": "Widget Line 1",
                "quantity": 1,
                "unit_price": Decimal("100.00"),
                "tax_id": tax.id,
            },
            {
                "product_id": product.id,
                "product_name": "Widget Line 2",
                "quantity": 1,
                "unit_price": Decimal("100.00"),
                "tax_id": tax.id,
            },
        ]

        with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", True):
            result = integrations.price_invoice_lines(input_lines, billing_date=today)

        # Both lines get the same product discount (id = prod_disc.id)
        # discount_lines has 2 entries with the same discount_id
        disc_lines = result["discount_lines"]
        self.assertEqual(len(disc_lines), 2)
        self.assertEqual(disc_lines[0]["discount_id"], prod_disc.id)
        self.assertEqual(disc_lines[1]["discount_id"], prod_disc.id)
        self.assertEqual(disc_lines[0]["amount"], Decimal("10.00"))
        self.assertEqual(disc_lines[1]["amount"], Decimal("10.00"))

        # Aggregation by discount_id yields one summed amount
        aggregated = {}
        for dl in disc_lines:
            d_id = dl["discount_id"]
            aggregated[d_id] = aggregated.get(d_id, Decimal("0.00")) + dl["amount"]

        self.assertEqual(len(aggregated), 1)
        self.assertEqual(aggregated[prod_disc.id], Decimal("20.00"))

        # Sum of line discount_amount equals totals.discount_total
        sum_line_discounts = sum(l["discount_amount"] for l in result["lines"])
        self.assertEqual(sum_line_discounts, result["totals"]["discount_total"])
        self.assertEqual(sum_line_discounts, Decimal("20.00"))

    # -------------------------------------------------------------------------
    # 6. redeem_discounts Tests
    # -------------------------------------------------------------------------
    def test_redeem_discounts_stub_mode(self):
        from apps.billing import integrations

        with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", False):
            res = integrations.redeem_discounts([1, 2, 2, 3], invoice_id=10, subscription_id=20)
            self.assertTrue(res["all_recorded"])
            self.assertEqual(res["failed_ids"], [])

    def test_redeem_discounts_deduplicates_and_records(self):
        from apps.billing import integrations

        mock_catalog = MagicMock()
        mock_catalog.record_discount_usage.return_value = True

        with patch.dict(sys.modules, {"apps.catalog.services": mock_catalog}):
            with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", True):
                res = integrations.redeem_discounts([5, 10, 5, 20, 10], invoice_id=101, subscription_id=505)

        # Called once per distinct id in ascending sorted order: 5, 10, 20
        self.assertEqual(mock_catalog.record_discount_usage.call_count, 3)
        self.assertEqual(
            mock_catalog.record_discount_usage.call_args_list,
            [
                call(5, 101, 505),
                call(10, 101, 505),
                call(20, 101, 505),
            ],
        )
        self.assertTrue(res["all_recorded"])
        self.assertEqual(res["failed_ids"], [])

    def test_redeem_discounts_sorts_ids_ascending(self):
        from apps.billing import integrations

        mock_catalog = MagicMock()
        mock_catalog.record_discount_usage.return_value = True

        with patch.dict(sys.modules, {"apps.catalog.services": mock_catalog}):
            with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", True):
                res = integrations.redeem_discounts([3, 1, 2], invoice_id=101, subscription_id=505)

        self.assertEqual(
            mock_catalog.record_discount_usage.call_args_list,
            [
                call(1, 101, 505),
                call(2, 101, 505),
                call(3, 101, 505),
            ],
        )
        self.assertTrue(res["all_recorded"])
        self.assertEqual(res["failed_ids"], [])

    def test_redeem_discounts_partial_failure_reports_failed_ids(self):
        from apps.billing import integrations

        def fake_record(d_id, inv_id, sub_id):
            return d_id != 10

        mock_catalog = MagicMock()
        mock_catalog.record_discount_usage.side_effect = fake_record

        with patch.dict(sys.modules, {"apps.catalog.services": mock_catalog}):
            with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", True):
                res = integrations.redeem_discounts([5, 10, 20], invoice_id=102, subscription_id=506)

        self.assertFalse(res["all_recorded"])
        self.assertEqual(res["failed_ids"], [10])


# =============================================================================
# Confirm and Cancel Invoice Service Tests (Task 3)
# =============================================================================
class ConfirmAndCancelServiceTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="service_test_customer@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )

    def _create_invoice(
        self,
        subscription_id=200,
        status=Invoice.Status.DRAFT,
        subtotal=Decimal("100.00"),
        discount_total=Decimal("0.00"),
        tax_total=Decimal("10.00"),
        total=Decimal("110.00"),
        amount_paid=Decimal("0.00"),
    ):
        today = timezone.localdate()
        return Invoice.objects.create(
            customer=self.customer,
            subscription_id=subscription_id,
            status=status,
            subtotal=subtotal,
            discount_total=discount_total,
            tax_total=tax_total,
            total=total,
            amount_paid=amount_paid,
            issue_date=today,
            due_date=today + timedelta(days=14),
            period_start=today,
            period_end=today + timedelta(days=30),
        )

    def test_confirm_draft_with_no_discounts(self):
        from apps.billing import integrations
        from apps.billing.services import ConfirmResult, confirm_invoice

        invoice = self._create_invoice()
        InvoiceLine.objects.create(
            invoice=invoice,
            product_name="Product No Discount",
            quantity=1,
            unit_price=Decimal("100.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("10.00"),
        )

        with patch.object(integrations, "redeem_discounts") as mock_redeem:
            result = confirm_invoice(invoice)

        self.assertIsInstance(result, ConfirmResult)
        self.assertFalse(result.amounts_changed)
        self.assertEqual(result.invoice.status, Invoice.Status.CONFIRMED)
        mock_redeem.assert_not_called()

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)

    def test_confirm_draft_accepts_pk(self):
        from apps.billing.services import ConfirmResult, confirm_invoice

        invoice = self._create_invoice()
        InvoiceLine.objects.create(
            invoice=invoice,
            product_name="Product",
            quantity=1,
            unit_price=Decimal("100.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("10.00"),
        )

        result = confirm_invoice(invoice.id)
        self.assertIsInstance(result, ConfirmResult)
        self.assertEqual(result.invoice.id, invoice.id)
        self.assertEqual(result.invoice.status, Invoice.Status.CONFIRMED)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)

    def test_confirm_draft_with_discounts_refuses_when_real_discount_usage_is_false(self):
        from apps.billing import integrations
        from apps.billing.services import confirm_invoice

        invoice = self._create_invoice(discount_total=Decimal("10.00"), total=Decimal("100.00"))
        InvoiceLine.objects.create(
            invoice=invoice,
            product_name="Discounted Line",
            quantity=1,
            unit_price=Decimal("100.00"),
            discount_amount=Decimal("10.00"),
            tax_amount=Decimal("10.00"),
        )
        InvoiceDiscount.objects.create(
            invoice=invoice,
            discount_id=1,
            amount=Decimal("10.00"),
        )

        with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", False):
            with patch.object(integrations, "redeem_discounts") as mock_redeem:
                with self.assertRaises(ValidationError) as ctx:
                    confirm_invoice(invoice)
                self.assertIn("USE_REAL_DISCOUNT_USAGE is False", str(ctx.exception))
                mock_redeem.assert_not_called()

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.DRAFT)

    def test_confirm_draft_with_discounts_succeeds_when_real_discount_usage_is_true(self):
        from apps.billing import integrations
        from apps.billing.services import ConfirmResult, confirm_invoice

        invoice = self._create_invoice(discount_total=Decimal("35.00"), total=Decimal("75.00"))
        InvoiceLine.objects.create(
            invoice=invoice,
            product_name="Multi Discount Line",
            quantity=1,
            unit_price=Decimal("100.00"),
            discount_amount=Decimal("35.00"),
            tax_amount=Decimal("10.00"),
        )
        InvoiceDiscount.objects.create(invoice=invoice, discount_id=20, amount=Decimal("10.00"))
        InvoiceDiscount.objects.create(invoice=invoice, discount_id=5, amount=Decimal("15.00"))
        InvoiceDiscount.objects.create(invoice=invoice, discount_id=10, amount=Decimal("10.00"))

        with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", True):
            with patch.object(
                integrations,
                "redeem_discounts",
                return_value={"all_recorded": True, "failed_ids": []},
            ) as mock_redeem:
                result = confirm_invoice(invoice)

        self.assertIsInstance(result, ConfirmResult)
        self.assertFalse(result.amounts_changed)
        self.assertEqual(result.invoice.status, Invoice.Status.CONFIRMED)
        # Redeemed with sorted ascending IDs [5, 10, 20]
        mock_redeem.assert_called_once_with([5, 10, 20], invoice.id, invoice.subscription_id)

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)

    def test_confirm_reprices_and_retries_on_discount_failure(self):
        from apps.billing import integrations
        from apps.billing.services import ConfirmResult, confirm_invoice

        invoice = self._create_invoice(
            subtotal=Decimal("100.00"),
            discount_total=Decimal("20.00"),
            tax_total=Decimal("8.00"),
            total=Decimal("88.00"),
        )
        line = InvoiceLine.objects.create(
            invoice=invoice,
            product_id=10,
            product_name="Product",
            quantity=1,
            unit_price=Decimal("100.00"),
            discount_amount=Decimal("20.00"),
            tax_amount=Decimal("8.00"),
        )
        InvoiceDiscount.objects.create(
            invoice=invoice,
            discount_id=1,
            amount=Decimal("20.00"),
        )

        priced_return = {
            "lines": [
                {
                    "product_id": 10,
                    "variant_id": None,
                    "product_name": "Product",
                    "quantity": 1,
                    "unit_price": Decimal("100.00"),
                    "discount_id": None,
                    "discount_amount": Decimal("0.00"),
                    "tax_amount": Decimal("10.00"),
                    "tax_id": None,
                    "line_total": Decimal("110.00"),
                }
            ],
            "discount_lines": [],
            "totals": {
                "subtotal": Decimal("100.00"),
                "discount_total": Decimal("0.00"),
                "tax_total": Decimal("10.00"),
                "total": Decimal("110.00"),
            },
        }

        with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", True):
            with patch.object(integrations, "USE_REAL_PRICING", True):
                with patch.object(
                    integrations,
                    "redeem_discounts",
                    return_value={"all_recorded": False, "failed_ids": [1]},
                ) as mock_redeem:
                    with patch.object(
                        integrations,
                        "price_invoice_lines",
                        return_value=priced_return,
                    ) as mock_price:
                        result = confirm_invoice(invoice)

        self.assertIsInstance(result, ConfirmResult)
        self.assertTrue(result.amounts_changed)
        self.assertEqual(result.invoice.status, Invoice.Status.CONFIRMED)
        self.assertEqual(result.invoice.total, Decimal("110.00"))
        self.assertEqual(result.invoice.discount_total, Decimal("0.00"))
        self.assertEqual(result.invoice.tax_total, Decimal("10.00"))
        self.assertEqual(result.invoice.discounts.count(), 0)

        # Stored unit price was passed to price_invoice_lines
        mock_price.assert_called_once()
        passed_lines = mock_price.call_args[0][0]
        self.assertEqual(passed_lines[0]["unit_price"], Decimal("100.00"))

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)
        self.assertEqual(invoice.total, Decimal("110.00"))
        line.refresh_from_db()
        self.assertEqual(line.discount_amount, Decimal("0.00"))
        self.assertEqual(line.tax_amount, Decimal("10.00"))

    def test_confirm_reprice_retry_also_fails_raises_validation_error_and_rolls_back(self):
        from apps.billing import integrations
        from apps.billing.services import confirm_invoice

        invoice = self._create_invoice(
            subtotal=Decimal("100.00"),
            discount_total=Decimal("20.00"),
            tax_total=Decimal("8.00"),
            total=Decimal("88.00"),
        )
        line = InvoiceLine.objects.create(
            invoice=invoice,
            product_id=10,
            product_name="Product",
            quantity=1,
            unit_price=Decimal("100.00"),
            discount_amount=Decimal("20.00"),
            tax_amount=Decimal("8.00"),
        )
        InvoiceDiscount.objects.create(
            invoice=invoice,
            discount_id=1,
            amount=Decimal("20.00"),
        )

        priced_return = {
            "lines": [
                {
                    "product_id": 10,
                    "variant_id": None,
                    "product_name": "Product",
                    "quantity": 1,
                    "unit_price": Decimal("100.00"),
                    "discount_id": 2,
                    "discount_amount": Decimal("10.00"),
                    "tax_amount": Decimal("9.00"),
                    "tax_id": None,
                    "line_total": Decimal("99.00"),
                }
            ],
            "discount_lines": [
                {
                    "discount_id": 2,
                    "description": "Discount 2",
                    "amount": Decimal("10.00"),
                    "line_index": 0,
                }
            ],
            "totals": {
                "subtotal": Decimal("100.00"),
                "discount_total": Decimal("10.00"),
                "tax_total": Decimal("9.00"),
                "total": Decimal("99.00"),
            },
        }

        # Both redeem attempts fail
        with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", True):
            with patch.object(integrations, "USE_REAL_PRICING", True):
                with patch.object(
                    integrations,
                    "redeem_discounts",
                    side_effect=[
                        {"all_recorded": False, "failed_ids": [1]},
                        {"all_recorded": False, "failed_ids": [2]},
                    ],
                ):
                    with patch.object(
                        integrations,
                        "price_invoice_lines",
                        return_value=priced_return,
                    ):
                        with self.assertRaises(ValidationError) as ctx:
                            confirm_invoice(invoice)
                        self.assertIn("discount no longer available, please retry", str(ctx.exception))

        # Check that DB was rolled back cleanly to draft state with original amounts
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.DRAFT)
        self.assertEqual(invoice.total, Decimal("88.00"))
        self.assertEqual(invoice.discount_total, Decimal("20.00"))
        self.assertEqual(invoice.discounts.count(), 1)
        self.assertEqual(invoice.discounts.first().discount_id, 1)
        line.refresh_from_db()
        self.assertEqual(line.discount_amount, Decimal("20.00"))

    def test_confirm_fails_when_reprice_needed_but_use_real_pricing_is_false(self):
        from apps.billing import integrations
        from apps.billing.services import confirm_invoice

        invoice = self._create_invoice(
            subtotal=Decimal("100.00"),
            discount_total=Decimal("20.00"),
            tax_total=Decimal("8.00"),
            total=Decimal("88.00"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            product_id=10,
            product_name="Product",
            quantity=1,
            unit_price=Decimal("100.00"),
            discount_amount=Decimal("20.00"),
            tax_amount=Decimal("8.00"),
        )
        InvoiceDiscount.objects.create(
            invoice=invoice,
            discount_id=1,
            amount=Decimal("20.00"),
        )

        with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", True):
            with patch.object(integrations, "USE_REAL_PRICING", False):
                with patch.object(
                    integrations,
                    "redeem_discounts",
                    return_value={"all_recorded": False, "failed_ids": [1]},
                ):
                    with self.assertRaises(ValidationError) as ctx:
                        confirm_invoice(invoice)
                    self.assertIn("USE_REAL_PRICING is False", str(ctx.exception))

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.DRAFT)
        self.assertEqual(invoice.total, Decimal("88.00"))

    def test_confirm_non_draft_raises_illegal_status_transition_error(self):
        from apps.billing.models import IllegalStatusTransitionError
        from apps.billing.services import confirm_invoice

        for idx, non_draft_status in enumerate([
            Invoice.Status.CONFIRMED,
            Invoice.Status.PAID,
            Invoice.Status.CANCELLED,
        ]):
            invoice = self._create_invoice(subscription_id=300 + idx, status=non_draft_status)
            with self.assertRaises(IllegalStatusTransitionError) as ctx:
                confirm_invoice(invoice)
            self.assertIn(f"current status is '{non_draft_status}'", str(ctx.exception))
            self.assertIn(f"only '{Invoice.Status.DRAFT}' invoices can be confirmed", str(ctx.exception))

    def test_cancel_invoice_service(self):
        from apps.billing.models import IllegalStatusTransitionError
        from apps.billing.services import cancel_invoice

        # 1. Cancel DRAFT invoice
        draft_inv = self._create_invoice(subscription_id=401, status=Invoice.Status.DRAFT)
        res_draft = cancel_invoice(draft_inv)
        self.assertEqual(res_draft.status, Invoice.Status.CANCELLED)
        draft_inv.refresh_from_db()
        self.assertEqual(draft_inv.status, Invoice.Status.CANCELLED)

        # 2. Cancel CONFIRMED invoice via pk
        conf_inv = self._create_invoice(subscription_id=402, status=Invoice.Status.CONFIRMED)
        res_conf = cancel_invoice(conf_inv.id)
        self.assertEqual(res_conf.status, Invoice.Status.CANCELLED)
        conf_inv.refresh_from_db()
        self.assertEqual(conf_inv.status, Invoice.Status.CANCELLED)

        # 3. Blocked when amount_paid > 0
        part_paid = self._create_invoice(
            subscription_id=403,
            status=Invoice.Status.CONFIRMED,
            amount_paid=Decimal("25.00"),
        )
        with self.assertRaises(IllegalStatusTransitionError) as ctx:
            cancel_invoice(part_paid)
        self.assertIn("amount_paid = 25.00", str(ctx.exception))
        part_paid.refresh_from_db()
        self.assertEqual(part_paid.status, Invoice.Status.CONFIRMED)

        # 4. Blocked if already CANCELLED
        with self.assertRaises(IllegalStatusTransitionError):
            cancel_invoice(draft_inv)


# =============================================================================
# Rollback-Proof and Invoice Generation Tests (Tasks 1.5 & 2)
# =============================================================================

class ConfirmInvoiceRollbackProofTests(TransactionTestCase):
    def test_confirm_invoice_rollback_proof_discards_first_attempt_side_effects(self):
        from apps.billing import integrations
        from apps.billing.models import Invoice, InvoiceDiscount, InvoiceLine
        from apps.billing.services import confirm_invoice

        customer = User.objects.create_user(
            email="rollback_proof_customer@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )
        today = timezone.localdate()
        invoice = Invoice.objects.create(
            customer=customer,
            subscription_id=777,
            status=Invoice.Status.DRAFT,
            subtotal=Decimal("100.00"),
            discount_total=Decimal("20.00"),
            tax_total=Decimal("8.00"),
            total=Decimal("88.00"),
            issue_date=today,
            due_date=today + timedelta(days=14),
            period_start=today,
            period_end=today + timedelta(days=30),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            product_id=1,
            product_name="Rollback Item",
            quantity=1,
            unit_price=Decimal("100.00"),
            discount_amount=Decimal("20.00"),
            tax_amount=Decimal("8.00"),
        )
        InvoiceDiscount.objects.create(invoice=invoice, discount_id=101, amount=Decimal("10.00"))
        InvoiceDiscount.objects.create(invoice=invoice, discount_id=102, amount=Decimal("10.00"))

        dummy_email = "side_effect_dummy_row@example.com"
        self.assertFalse(User.objects.filter(email=dummy_email).exists())

        def mock_record(d_id, inv_id, sub_id):
            if d_id == 101:
                # First discount records and creates a dummy DB row via ORM
                User.objects.create_user(
                    email=dummy_email,
                    password="password123",
                    role=User.Role.CUSTOMER,
                )
                return True
            elif d_id == 102:
                # Second discount fails, triggering abort of first atomic attempt!
                return False
            return True

        priced_without_discounts = {
            "lines": [
                {
                    "product_id": 1,
                    "variant_id": None,
                    "product_name": "Rollback Item",
                    "quantity": 1,
                    "unit_price": Decimal("100.00"),
                    "discount_id": None,
                    "discount_amount": Decimal("0.00"),
                    "tax_amount": Decimal("10.00"),
                    "tax_id": None,
                    "line_total": Decimal("110.00"),
                }
            ],
            "discount_lines": [],
            "totals": {
                "subtotal": Decimal("100.00"),
                "discount_total": Decimal("0.00"),
                "tax_total": Decimal("10.00"),
                "total": Decimal("110.00"),
            },
        }

        mock_catalog = MagicMock()
        mock_catalog.record_discount_usage.side_effect = mock_record

        with patch.dict(sys.modules, {"apps.catalog.services": mock_catalog}):
            with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", True):
                with patch.object(integrations, "USE_REAL_PRICING", True):
                    with patch.object(
                        integrations,
                        "price_invoice_lines",
                        return_value=priced_without_discounts,
                    ):
                        result = confirm_invoice(invoice)

        self.assertTrue(result.amounts_changed)
        self.assertEqual(result.invoice.status, Invoice.Status.CONFIRMED)
        self.assertEqual(result.invoice.total, Decimal("110.00"))

        # The dummy row created during the FIRST attempt's atomic block MUST BE GONE
        self.assertFalse(
            User.objects.filter(email=dummy_email).exists(),
            "Dummy row from aborted first attempt was not rolled back!",
        )


class FakeSubscriptionsService:
    def __init__(self, due_data: list):
        self.queues = {}
        for item in due_data:
            self.queues.setdefault(item["id"], []).append(item)
        self.advanced_calls = []

    def get_due_subscriptions(self, target_date=None):
        results = []
        for sub_id, queue in self.queues.items():
            if queue:
                results.append(queue[0])
        return results

    def advance_next_billing_date(self, subscription_id):
        self.advanced_calls.append(subscription_id)
        if self.queues.get(subscription_id):
            self.queues[subscription_id].pop(0)
        return {"subscription_id": subscription_id, "status": "ACTIVE"}


class InvoiceGenerationServiceTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="gen_customer@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )

    def _default_priced(self, lines, billing_date=None):
        subtotal = Decimal("0.00")
        priced_lines = []
        for l in lines:
            qty = Decimal(l.get("quantity", 1))
            price = Decimal(str(l.get("unit_price", "0.00")))
            line_sub = (qty * price).quantize(Decimal("0.01"))
            subtotal += line_sub
            priced_lines.append({
                "product_id": l.get("product_id"),
                "variant_id": l.get("variant_id"),
                "product_name": l.get("product_name", "Test Item"),
                "quantity": int(qty),
                "unit_price": price,
                "discount_amount": Decimal("0.00"),
                "tax_amount": Decimal("0.00"),
                "tax_id": l.get("tax_id"),
                "line_total": line_sub,
            })
        return {
            "lines": priced_lines,
            "discount_lines": [],
            "totals": {
                "subtotal": subtotal,
                "discount_total": Decimal("0.00"),
                "tax_total": Decimal("0.00"),
                "total": subtotal,
            },
        }

    def test_generate_one_subscription_one_period(self):
        from apps.billing import integrations
        from apps.billing.models import Invoice
        from apps.billing.services import generate_invoices

        lines = [
            {
                "product_id": 1,
                "product_name": "Basic SaaS Plan",
                "quantity": 1,
                "unit_price": Decimal("50.00"),
                "tax_id": None,
            }
        ]
        due = [
            {
                "id": 10,
                "customer_id": self.customer.id,
                "period_start": date(2026, 1, 1),
                "period_end": date(2026, 1, 31),
                "lines": lines,
                "payment_terms_days": 15,
            }
        ]
        fake = FakeSubscriptionsService(due)

        with patch.object(integrations, "get_due_subscriptions", side_effect=fake.get_due_subscriptions):
            with patch.object(integrations, "advance_next_billing_date", side_effect=fake.advance_next_billing_date):
                with patch.object(integrations, "price_invoice_lines", side_effect=self._default_priced):
                    summary = generate_invoices()

        self.assertEqual(summary.created, 1)
        self.assertEqual(summary.skipped_existing, 0)
        self.assertEqual(summary.advanced, 1)
        self.assertEqual(summary.errors, [])
        self.assertEqual(summary.capped, [])

        inv = Invoice.objects.get(subscription_id=10)
        self.assertEqual(inv.status, Invoice.Status.DRAFT)
        self.assertEqual(inv.total, Decimal("50.00"))
        self.assertEqual(inv.lines.count(), 1)
        self.assertEqual(inv.due_date, inv.issue_date + timedelta(days=15))
        self.assertEqual(fake.advanced_calls, [10])

    def test_generate_run_twice_with_fake_unadvanced(self):
        from apps.billing import integrations
        from apps.billing.models import Invoice
        from apps.billing.services import generate_invoices

        item = {
            "id": 15,
            "customer_id": self.customer.id,
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 1, 31),
            "lines": [{"product_id": 1, "unit_price": Decimal("30.00"), "quantity": 1}],
        }
        fake = FakeSubscriptionsService([item])

        with patch.object(integrations, "get_due_subscriptions", side_effect=fake.get_due_subscriptions):
            with patch.object(integrations, "advance_next_billing_date", side_effect=fake.advance_next_billing_date):
                with patch.object(integrations, "price_invoice_lines", side_effect=self._default_priced):
                    summary1 = generate_invoices()

        self.assertEqual(summary1.created, 1)
        self.assertEqual(summary1.advanced, 1)
        self.assertEqual(Invoice.objects.filter(subscription_id=15).count(), 1)

        # Run 2: fake un-advanced (period 1 still in queue)
        fake.queues[15] = [item]

        with patch.object(integrations, "get_due_subscriptions", side_effect=fake.get_due_subscriptions):
            with patch.object(integrations, "advance_next_billing_date", side_effect=fake.advance_next_billing_date):
                with patch.object(integrations, "price_invoice_lines", side_effect=self._default_priced):
                    summary2 = generate_invoices()

        self.assertEqual(summary2.created, 0)
        self.assertEqual(summary2.skipped_existing, 1)
        self.assertEqual(summary2.advanced, 1)
        self.assertEqual(Invoice.objects.filter(subscription_id=15).count(), 1)
        self.assertEqual(fake.advanced_calls, [15, 15])

    def test_generate_cancelled_invoice_allows_recreation(self):
        from apps.billing import integrations
        from apps.billing.models import Invoice
        from apps.billing.services import generate_invoices

        # Existing invoice for that period is CANCELLED
        today = timezone.localdate()
        Invoice.objects.create(
            customer=self.customer,
            subscription_id=25,
            status=Invoice.Status.CANCELLED,
            subtotal=Decimal("40.00"),
            discount_total=Decimal("0.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("40.00"),
            issue_date=today,
            due_date=today + timedelta(days=30),
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
        )

        item = {
            "id": 25,
            "customer_id": self.customer.id,
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 1, 31),
            "lines": [{"product_id": 1, "unit_price": Decimal("40.00"), "quantity": 1}],
        }
        fake = FakeSubscriptionsService([item])

        with patch.object(integrations, "get_due_subscriptions", side_effect=fake.get_due_subscriptions):
            with patch.object(integrations, "advance_next_billing_date", side_effect=fake.advance_next_billing_date):
                with patch.object(integrations, "price_invoice_lines", side_effect=self._default_priced):
                    summary = generate_invoices()

        self.assertEqual(summary.created, 1)
        self.assertEqual(summary.skipped_existing, 0)
        invoices = Invoice.objects.filter(subscription_id=25)
        self.assertEqual(invoices.count(), 2)
        self.assertEqual(invoices.filter(status=Invoice.Status.DRAFT).count(), 1)
        self.assertEqual(invoices.filter(status=Invoice.Status.CANCELLED).count(), 1)

    def test_generate_multi_period_catchup(self):
        from apps.billing import integrations
        from apps.billing.models import Invoice
        from apps.billing.services import generate_invoices

        lines = [{"product_id": 1, "unit_price": Decimal("20.00"), "quantity": 1}]
        p1 = {"id": 35, "customer_id": self.customer.id, "period_start": date(2026, 1, 1), "period_end": date(2026, 1, 31), "lines": lines}
        p2 = {"id": 35, "customer_id": self.customer.id, "period_start": date(2026, 2, 1), "period_end": date(2026, 2, 28), "lines": lines}
        p3 = {"id": 35, "customer_id": self.customer.id, "period_start": date(2026, 3, 1), "period_end": date(2026, 3, 31), "lines": lines}

        fake = FakeSubscriptionsService([p1, p2, p3])

        with patch.object(integrations, "get_due_subscriptions", side_effect=fake.get_due_subscriptions):
            with patch.object(integrations, "advance_next_billing_date", side_effect=fake.advance_next_billing_date):
                with patch.object(integrations, "price_invoice_lines", side_effect=self._default_priced):
                    summary = generate_invoices()

        self.assertEqual(summary.created, 3)
        self.assertEqual(summary.advanced, 3)
        invoices = list(Invoice.objects.filter(subscription_id=35).order_by("period_start"))
        self.assertEqual(len(invoices), 3)
        self.assertEqual(
            [i.period_start for i in invoices],
            [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)],
        )

    def test_generate_cap_limits_periods(self):
        from apps.billing import integrations
        from apps.billing.models import Invoice
        from apps.billing.services import generate_invoices

        lines = [{"product_id": 1, "unit_price": Decimal("20.00"), "quantity": 1}]
        periods = [
            {"id": 45, "customer_id": self.customer.id, "period_start": date(2026, m, 1), "period_end": date(2026, m, 28), "lines": lines}
            for m in range(1, 6)
        ]
        fake = FakeSubscriptionsService(periods)

        with patch.object(integrations, "get_due_subscriptions", side_effect=fake.get_due_subscriptions):
            with patch.object(integrations, "advance_next_billing_date", side_effect=fake.advance_next_billing_date):
                with patch.object(integrations, "price_invoice_lines", side_effect=self._default_priced):
                    summary = generate_invoices(max_periods_per_subscription=2)

        self.assertEqual(summary.created, 2)
        self.assertEqual(summary.capped, [45])
        self.assertEqual(Invoice.objects.filter(subscription_id=45).count(), 2)

    def test_generate_advance_raising_rolls_back_invoice(self):
        from apps.billing import integrations
        from apps.billing.models import Invoice
        from apps.billing.services import generate_invoices

        item = {
            "id": 55,
            "customer_id": self.customer.id,
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 1, 31),
            "lines": [{"product_id": 1, "unit_price": Decimal("25.00"), "quantity": 1}],
        }
        fake = FakeSubscriptionsService([item])

        def failing_advance(sub_id):
            raise RuntimeError("Advance network failure")

        with patch.object(integrations, "get_due_subscriptions", side_effect=fake.get_due_subscriptions):
            with patch.object(integrations, "advance_next_billing_date", side_effect=failing_advance):
                with patch.object(integrations, "price_invoice_lines", side_effect=self._default_priced):
                    summary = generate_invoices()

        self.assertEqual(summary.created, 0)
        self.assertEqual(summary.advanced, 0)
        self.assertEqual(len(summary.errors), 1)
        self.assertEqual(summary.errors[0]["subscription_id"], 55)
        # Invoice rolled back
        self.assertFalse(Invoice.objects.filter(subscription_id=55).exists())

    def test_generate_integrity_error_race(self):
        from apps.billing import integrations
        from apps.billing.models import Invoice
        from apps.billing.services import generate_invoices

        item = {
            "id": 65,
            "customer_id": self.customer.id,
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 1, 31),
            "lines": [{"product_id": 1, "unit_price": Decimal("35.00"), "quantity": 1}],
        }
        fake = FakeSubscriptionsService([item])

        def racing_pricing(lines, billing_date=None):
            # Concurrently insert an active invoice before pricing finishes
            today = timezone.localdate()
            Invoice.objects.create(
                customer=self.customer,
                subscription_id=65,
                period_start=date(2026, 1, 1),
                period_end=date(2026, 1, 31),
                issue_date=today,
                due_date=today + timedelta(days=30),
                status=Invoice.Status.DRAFT,
            )
            return self._default_priced(lines, billing_date)

        with patch.object(integrations, "get_due_subscriptions", side_effect=fake.get_due_subscriptions):
            with patch.object(integrations, "advance_next_billing_date", side_effect=fake.advance_next_billing_date):
                with patch.object(integrations, "price_invoice_lines", side_effect=racing_pricing):
                    summary = generate_invoices()

        self.assertEqual(summary.created, 0)
        self.assertEqual(summary.skipped_existing, 1)
        self.assertEqual(summary.advanced, 1)
        self.assertEqual(Invoice.objects.filter(subscription_id=65).count(), 1)
        self.assertEqual(fake.advanced_calls, [65])

    def test_generate_discount_aggregation(self):
        from apps.billing import integrations
        from apps.billing.models import Invoice
        from apps.billing.services import generate_invoices

        lines = [
            {"product_id": 1, "unit_price": Decimal("50.00"), "quantity": 1},
            {"product_id": 1, "unit_price": Decimal("50.00"), "quantity": 1},
        ]
        item = {
            "id": 75,
            "customer_id": self.customer.id,
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 1, 31),
            "lines": lines,
        }
        fake = FakeSubscriptionsService([item])

        def discounted_pricing(input_lines, billing_date=None):
            return {
                "lines": [
                    {
                        "product_id": 1,
                        "variant_id": None,
                        "product_name": "Item 1",
                        "quantity": 1,
                        "unit_price": Decimal("50.00"),
                        "discount_amount": Decimal("5.00"),
                        "tax_amount": Decimal("0.00"),
                        "tax_id": None,
                        "line_total": Decimal("45.00"),
                    },
                    {
                        "product_id": 1,
                        "variant_id": None,
                        "product_name": "Item 2",
                        "quantity": 1,
                        "unit_price": Decimal("50.00"),
                        "discount_amount": Decimal("5.00"),
                        "tax_amount": Decimal("0.00"),
                        "tax_id": None,
                        "line_total": Decimal("45.00"),
                    },
                ],
                "discount_lines": [
                    {"discount_id": 99, "description": "10% Promo", "amount": Decimal("5.00"), "line_index": 0},
                    {"discount_id": 99, "description": "10% Promo", "amount": Decimal("5.00"), "line_index": 1},
                ],
                "totals": {
                    "subtotal": Decimal("100.00"),
                    "discount_total": Decimal("10.00"),
                    "tax_total": Decimal("0.00"),
                    "total": Decimal("90.00"),
                },
            }

        with patch.object(integrations, "get_due_subscriptions", side_effect=fake.get_due_subscriptions):
            with patch.object(integrations, "advance_next_billing_date", side_effect=fake.advance_next_billing_date):
                with patch.object(integrations, "price_invoice_lines", side_effect=discounted_pricing):
                    summary = generate_invoices()

        self.assertEqual(summary.created, 1)
        inv = Invoice.objects.get(subscription_id=75)
        self.assertEqual(inv.total, Decimal("90.00"))
        self.assertEqual(inv.discount_total, Decimal("10.00"))
        # Exactly one InvoiceDiscount row aggregating the two lines
        self.assertEqual(inv.discounts.count(), 1)
        disc = inv.discounts.first()
        self.assertEqual(disc.discount_id, 99)
        self.assertEqual(disc.amount, Decimal("10.00"))

    def test_generate_subscription_with_no_lines(self):
        from apps.billing import integrations
        from apps.billing.services import generate_invoices

        item = {
            "id": 85,
            "customer_id": self.customer.id,
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 1, 31),
            "lines": [],
        }
        fake = FakeSubscriptionsService([item])

        with patch.object(integrations, "get_due_subscriptions", side_effect=fake.get_due_subscriptions):
            with patch.object(integrations, "advance_next_billing_date", side_effect=fake.advance_next_billing_date):
                summary = generate_invoices()

        self.assertEqual(summary.created, 0)
        self.assertEqual(summary.advanced, 0)
        self.assertEqual(len(summary.errors), 1)
        self.assertEqual(summary.errors[0]["error"], "no lines")
        self.assertEqual(fake.advanced_calls, [])

    def test_generate_invoices_stay_draft_and_confirm_not_called(self):
        from apps.billing import integrations
        from apps.billing.models import Invoice
        from apps.billing.services import generate_invoices

        item = {
            "id": 95,
            "customer_id": self.customer.id,
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 1, 31),
            "lines": [{"product_id": 1, "unit_price": Decimal("25.00"), "quantity": 1}],
        }
        fake = FakeSubscriptionsService([item])

        with patch("apps.billing.services.confirm_invoice") as mock_confirm:
            with patch.object(integrations, "get_due_subscriptions", side_effect=fake.get_due_subscriptions):
                with patch.object(integrations, "advance_next_billing_date", side_effect=fake.advance_next_billing_date):
                    with patch.object(integrations, "price_invoice_lines", side_effect=self._default_priced):
                        summary = generate_invoices()

        mock_confirm.assert_not_called()
        self.assertEqual(summary.created, 1)
        inv = Invoice.objects.get(subscription_id=95)
        self.assertEqual(inv.status, Invoice.Status.DRAFT)

    def test_generate_same_period_returned_after_advance_triggers_infinite_loop_guard(self):
        from apps.billing import integrations
        from apps.billing.services import generate_invoices

        item = {
            "id": 105,
            "customer_id": self.customer.id,
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 1, 31),
            "lines": [{"product_id": 1, "unit_price": Decimal("25.00"), "quantity": 1}],
        }
        # Buggy advance does NOT drop the period
        fake = FakeSubscriptionsService([item])
        def buggy_advance(sub_id):
            fake.advanced_calls.append(sub_id)
            return {"subscription_id": sub_id, "status": "ACTIVE"}

        with patch.object(integrations, "get_due_subscriptions", side_effect=fake.get_due_subscriptions):
            with patch.object(integrations, "advance_next_billing_date", side_effect=buggy_advance):
                with patch.object(integrations, "price_invoice_lines", side_effect=self._default_priced):
                    summary = generate_invoices()

        self.assertEqual(summary.created, 1)
        self.assertEqual(len(summary.errors), 1)
        self.assertIn("returned same period_start", summary.errors[0]["error"])


class InvoiceGenerationTransactionTests(TransactionTestCase):
    def test_generate_failure_isolation(self):
        from apps.billing import integrations
        from apps.billing.models import Invoice
        from apps.billing.services import generate_invoices

        cust = User.objects.create_user(
            email="iso_cust@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )
        sub_a = {
            "id": 801,
            "customer_id": cust.id,
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 1, 31),
            "lines": [{"product_id": 1, "unit_price": Decimal("50.00"), "quantity": 1}],
        }
        sub_b = {
            "id": 802,
            "customer_id": cust.id,
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 1, 31),
            "lines": [{"product_id": 999, "unit_price": Decimal("50.00"), "quantity": 1}],
        }
        fake = FakeSubscriptionsService([sub_a, sub_b])

        def selective_pricing(lines, billing_date=None):
            if lines and lines[0].get("product_id") == 999:
                raise RuntimeError("Catalog pricing service down for product 999")
            return {
                "lines": [
                    {
                        "product_id": lines[0].get("product_id"),
                        "variant_id": None,
                        "product_name": "Good Item",
                        "quantity": 1,
                        "unit_price": Decimal("50.00"),
                        "discount_amount": Decimal("0.00"),
                        "tax_amount": Decimal("0.00"),
                        "tax_id": None,
                        "line_total": Decimal("50.00"),
                    }
                ],
                "discount_lines": [],
                "totals": {
                    "subtotal": Decimal("50.00"),
                    "discount_total": Decimal("0.00"),
                    "tax_total": Decimal("0.00"),
                    "total": Decimal("50.00"),
                },
            }

        with patch.object(integrations, "get_due_subscriptions", side_effect=fake.get_due_subscriptions):
            with patch.object(integrations, "advance_next_billing_date", side_effect=fake.advance_next_billing_date):
                with patch.object(integrations, "price_invoice_lines", side_effect=selective_pricing):
                    summary = generate_invoices()

        # Failure isolation: Sub A succeeded and committed; Sub B failed with error
        self.assertEqual(summary.created, 1)
        self.assertEqual(len(summary.errors), 1)
        self.assertEqual(summary.errors[0]["subscription_id"], 802)
        self.assertTrue(Invoice.objects.filter(subscription_id=801).exists())
        self.assertFalse(Invoice.objects.filter(subscription_id=802).exists())
        self.assertIn(801, fake.advanced_calls)
        self.assertNotIn(802, fake.advanced_calls)
