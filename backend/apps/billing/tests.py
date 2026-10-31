import threading
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.utils import IntegrityError
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from .models import IllegalStatusTransitionError, Invoice, InvoiceLine, quantize_money

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
