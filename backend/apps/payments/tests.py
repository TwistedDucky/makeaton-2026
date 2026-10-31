from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.utils import IntegrityError
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.billing.models import Invoice
from .models import Payment, PaymentAllocation

User = get_user_model()


class PaymentModelTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="payer@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )
        self.staff_user = User.objects.create_user(
            email="staff@example.com",
            password="testpassword123",
            role=User.Role.STAFF,
        )
        self.invoice = Invoice.objects.create(
            customer=self.customer,
            subscription_id=500,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 15),
            total=Decimal("150.00"),
        )

    # Positive Payment Amount Validations
    def test_valid_payment_creation(self):
        payment = Payment.objects.create(
            customer=self.customer,
            method=Payment.Method.CARD,
            amount=Decimal("150.00"),
            recorded_by=self.staff_user,
            note="Test payment via card",
        )
        self.assertIsNotNone(payment.id)
        self.assertEqual(payment.amount, Decimal("150.00"))
        self.assertEqual(payment.method, Payment.Method.CARD)
        self.assertEqual(payment.payment_date, timezone.localdate())

    def test_payment_date_defaults_to_localdate(self):
        payment = Payment.objects.create(
            customer=self.customer,
            method=Payment.Method.UPI,
            amount=Decimal("50.00"),
            recorded_by=self.staff_user,
        )
        self.assertEqual(payment.payment_date, timezone.localdate())

    def test_payment_amount_zero_rejected_by_check_constraint(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Payment.objects.create(
                    customer=self.customer,
                    method=Payment.Method.UPI,
                    amount=Decimal("0.00"),
                    recorded_by=self.staff_user,
                )

    def test_payment_amount_zero_rejected_by_clean(self):
        payment = Payment(
            customer=self.customer,
            method=Payment.Method.UPI,
            amount=Decimal("0.00"),
            recorded_by=self.staff_user,
        )
        with self.assertRaises(ValidationError):
            payment.full_clean()

    def test_payment_amount_negative_rejected_by_check_constraint(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Payment.objects.create(
                    customer=self.customer,
                    method=Payment.Method.CASH,
                    amount=Decimal("-25.00"),
                    recorded_by=self.staff_user,
                )

    def test_payment_amount_negative_rejected_by_clean(self):
        payment = Payment(
            customer=self.customer,
            method=Payment.Method.CASH,
            amount=Decimal("-25.00"),
            recorded_by=self.staff_user,
        )
        with self.assertRaises(ValidationError):
            payment.full_clean()

    # Payment Allocation Tests
    def test_valid_payment_allocation(self):
        payment = Payment.objects.create(
            customer=self.customer,
            method=Payment.Method.BANK_TRANSFER,
            amount=Decimal("150.00"),
            recorded_by=self.staff_user,
        )
        allocation = PaymentAllocation.objects.create(
            payment=payment,
            invoice=self.invoice,
            amount=Decimal("150.00"),
        )
        self.assertIsNotNone(allocation.id)
        self.assertEqual(allocation.amount, Decimal("150.00"))
        self.assertEqual(allocation.invoice, self.invoice)

    def test_allocation_amount_zero_rejected_by_check_constraint(self):
        payment = Payment.objects.create(
            customer=self.customer,
            method=Payment.Method.BANK_TRANSFER,
            amount=Decimal("150.00"),
            recorded_by=self.staff_user,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PaymentAllocation.objects.create(
                    payment=payment,
                    invoice=self.invoice,
                    amount=Decimal("0.00"),
                )

    def test_allocation_amount_negative_rejected_by_check_constraint(self):
        payment = Payment.objects.create(
            customer=self.customer,
            method=Payment.Method.BANK_TRANSFER,
            amount=Decimal("150.00"),
            recorded_by=self.staff_user,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PaymentAllocation.objects.create(
                    payment=payment,
                    invoice=self.invoice,
                    amount=Decimal("-50.00"),
                )

    def test_duplicate_payment_invoice_allocation_rejected_by_unique_constraint(self):
        payment = Payment.objects.create(
            customer=self.customer,
            method=Payment.Method.CARD,
            amount=Decimal("150.00"),
            recorded_by=self.staff_user,
        )
        PaymentAllocation.objects.create(
            payment=payment,
            invoice=self.invoice,
            amount=Decimal("75.00"),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PaymentAllocation.objects.create(
                    payment=payment,
                    invoice=self.invoice,
                    amount=Decimal("75.00"),
                )


class RecordPaymentServiceTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="cust_pay_test@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )
        self.other_customer = User.objects.create_user(
            email="other_pay_test@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )
        self.staff_user = User.objects.create_user(
            email="staff_pay_test@example.com",
            password="testpassword123",
            role=User.Role.STAFF,
        )

    def _create_invoice(
        self,
        customer=None,
        status=Invoice.Status.CONFIRMED,
        total=Decimal("100.00"),
        amount_paid=Decimal("0.00"),
        due_date=None,
        subscription_id=None,
    ):
        if subscription_id is None:
            self._sub_counter = getattr(self, "_sub_counter", 100) + 1
            subscription_id = self._sub_counter
        return Invoice.objects.create(
            customer=customer or self.customer,
            subscription_id=subscription_id,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            issue_date=date(2026, 1, 1),
            due_date=due_date or date(2026, 2, 15),
            status=status,
            total=total,
            amount_paid=amount_paid,
        )

    def test_full_payment_marks_invoice_paid(self):
        from apps.payments.services import record_payment

        invoice = self._create_invoice(total=Decimal("150.00"), amount_paid=Decimal("0.00"))
        payment = record_payment(
            customer_id=self.customer.id,
            method=Payment.Method.CARD,
            amount=Decimal("150.00"),
            payment_date=date(2026, 2, 10),
            allocations=[{"invoice_id": invoice.id, "amount": Decimal("150.00")}],
            note="Full settlement",
            recorded_by=self.staff_user,
        )

        self.assertIsNotNone(payment.id)
        self.assertEqual(payment.amount, Decimal("150.00"))
        self.assertEqual(payment.allocations.count(), 1)
        alloc = payment.allocations.first()
        self.assertEqual(alloc.amount, Decimal("150.00"))
        self.assertEqual(alloc.invoice_id, invoice.id)

        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, Decimal("150.00"))
        self.assertEqual(invoice.status, Invoice.Status.PAID)

    def test_partial_payment_leaves_invoice_confirmed(self):
        from apps.payments.services import record_payment

        invoice = self._create_invoice(total=Decimal("200.00"), amount_paid=Decimal("0.00"))
        payment1 = record_payment(
            customer_id=self.customer.id,
            method=Payment.Method.UPI,
            amount=Decimal("80.00"),
            allocations=[{"invoice_id": invoice.id, "amount": Decimal("80.00")}],
            recorded_by=self.staff_user,
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)
        self.assertEqual(invoice.amount_paid, Decimal("80.00"))

        payment2 = record_payment(
            customer_id=self.customer.id,
            method=Payment.Method.CASH,
            amount=Decimal("50.00"),
            allocations=[{"invoice_id": invoice.id, "amount": Decimal("50.00")}],
            recorded_by=self.staff_user,
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)
        self.assertEqual(invoice.amount_paid, Decimal("130.00"))

    def test_multi_invoice_split_works(self):
        from apps.payments.services import record_payment

        inv1 = self._create_invoice(total=Decimal("100.00"), amount_paid=Decimal("0.00"))
        inv2 = self._create_invoice(total=Decimal("150.00"), amount_paid=Decimal("50.00"))

        payment = record_payment(
            customer_id=self.customer.id,
            method=Payment.Method.BANK_TRANSFER,
            amount=Decimal("160.00"),
            allocations=[
                {"invoice_id": inv1.id, "amount": Decimal("100.00")},
                {"invoice_id": inv2.id, "amount": Decimal("60.00")},
            ],
            recorded_by=self.staff_user,
        )

        self.assertEqual(payment.allocations.count(), 2)
        inv1.refresh_from_db()
        inv2.refresh_from_db()

        # inv1 fully paid -> PAID
        self.assertEqual(inv1.amount_paid, Decimal("100.00"))
        self.assertEqual(inv1.status, Invoice.Status.PAID)

        # inv2 partially paid (50 + 60 = 110 of 150) -> CONFIRMED
        self.assertEqual(inv2.amount_paid, Decimal("110.00"))
        self.assertEqual(inv2.status, Invoice.Status.CONFIRMED)

    def test_overpayment_rejected_with_nothing_written(self):
        from apps.payments.services import record_payment

        invoice = self._create_invoice(total=Decimal("100.00"), amount_paid=Decimal("60.00"))
        with self.assertRaises(ValidationError):
            record_payment(
                customer_id=self.customer.id,
                method=Payment.Method.CARD,
                amount=Decimal("45.00"),
                allocations=[{"invoice_id": invoice.id, "amount": Decimal("45.00")}],
                recorded_by=self.staff_user,
            )

        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(PaymentAllocation.objects.count(), 0)
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, Decimal("60.00"))
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)

    def test_wrong_customer_rejected(self):
        from apps.payments.services import record_payment

        invoice = self._create_invoice(customer=self.other_customer, total=Decimal("100.00"))
        with self.assertRaises(ValidationError):
            record_payment(
                customer_id=self.customer.id,
                method=Payment.Method.CARD,
                amount=Decimal("100.00"),
                allocations=[{"invoice_id": invoice.id, "amount": Decimal("100.00")}],
                recorded_by=self.staff_user,
            )

        self.assertEqual(Payment.objects.count(), 0)

    def test_draft_invoice_rejected(self):
        from apps.payments.services import record_payment

        invoice = self._create_invoice(status=Invoice.Status.DRAFT, total=Decimal("100.00"))
        with self.assertRaises(ValidationError):
            record_payment(
                customer_id=self.customer.id,
                method=Payment.Method.CARD,
                amount=Decimal("100.00"),
                allocations=[{"invoice_id": invoice.id, "amount": Decimal("100.00")}],
                recorded_by=self.staff_user,
            )

    def test_cancelled_invoice_rejected(self):
        from apps.payments.services import record_payment

        invoice = self._create_invoice(status=Invoice.Status.CANCELLED, total=Decimal("100.00"))
        with self.assertRaises(ValidationError):
            record_payment(
                customer_id=self.customer.id,
                method=Payment.Method.CARD,
                amount=Decimal("100.00"),
                allocations=[{"invoice_id": invoice.id, "amount": Decimal("100.00")}],
                recorded_by=self.staff_user,
            )

    def test_paid_invoice_rejected(self):
        from apps.payments.services import record_payment

        invoice = self._create_invoice(
            status=Invoice.Status.PAID,
            total=Decimal("100.00"),
            amount_paid=Decimal("100.00"),
        )
        with self.assertRaises(ValidationError):
            record_payment(
                customer_id=self.customer.id,
                method=Payment.Method.CARD,
                amount=Decimal("50.00"),
                allocations=[{"invoice_id": invoice.id, "amount": Decimal("50.00")}],
                recorded_by=self.staff_user,
            )

    def test_duplicate_invoice_ids_rejected(self):
        from apps.payments.services import record_payment

        invoice = self._create_invoice(total=Decimal("100.00"))
        with self.assertRaises(ValidationError):
            record_payment(
                customer_id=self.customer.id,
                method=Payment.Method.CARD,
                amount=Decimal("100.00"),
                allocations=[
                    {"invoice_id": invoice.id, "amount": Decimal("50.00")},
                    {"invoice_id": invoice.id, "amount": Decimal("50.00")},
                ],
                recorded_by=self.staff_user,
            )

    def test_allocation_sum_mismatch_rejected(self):
        from apps.payments.services import record_payment

        invoice = self._create_invoice(total=Decimal("100.00"))
        with self.assertRaises(ValidationError):
            record_payment(
                customer_id=self.customer.id,
                method=Payment.Method.CARD,
                amount=Decimal("100.00"),
                allocations=[{"invoice_id": invoice.id, "amount": Decimal("80.00")}],
                recorded_by=self.staff_user,
            )

    def test_amount_less_than_or_equal_to_zero_rejected(self):
        from apps.payments.services import record_payment

        invoice = self._create_invoice(total=Decimal("100.00"))
        with self.assertRaises(ValidationError):
            record_payment(
                customer_id=self.customer.id,
                method=Payment.Method.CARD,
                amount=Decimal("0.00"),
                allocations=[{"invoice_id": invoice.id, "amount": Decimal("0.00")}],
                recorded_by=self.staff_user,
            )

        with self.assertRaises(ValidationError):
            record_payment(
                customer_id=self.customer.id,
                method=Payment.Method.CARD,
                amount=Decimal("-10.00"),
                allocations=[{"invoice_id": invoice.id, "amount": Decimal("-10.00")}],
                recorded_by=self.staff_user,
            )

    def test_atomicity_second_invoice_failure_rolls_back_first(self):
        from apps.payments.services import record_payment

        inv1 = self._create_invoice(total=Decimal("100.00"), amount_paid=Decimal("0.00"))
        inv2 = self._create_invoice(
            customer=self.other_customer,
            total=Decimal("50.00"),
            amount_paid=Decimal("0.00"),
        )

        with self.assertRaises(ValidationError):
            record_payment(
                customer_id=self.customer.id,
                method=Payment.Method.CARD,
                amount=Decimal("150.00"),
                allocations=[
                    {"invoice_id": inv1.id, "amount": Decimal("100.00")},
                    {"invoice_id": inv2.id, "amount": Decimal("50.00")},
                ],
                recorded_by=self.staff_user,
            )

        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(PaymentAllocation.objects.count(), 0)
        inv1.refresh_from_db()
        self.assertEqual(inv1.amount_paid, Decimal("0.00"))
        self.assertEqual(inv1.status, Invoice.Status.CONFIRMED)

    def test_mark_zero_total_invoice_paid_helper(self):
        from apps.payments.services import mark_zero_total_invoice_paid

        zero_inv = self._create_invoice(total=Decimal("0.00"), amount_paid=Decimal("0.00"))
        mark_zero_total_invoice_paid(zero_inv.id)
        zero_inv.refresh_from_db()
        self.assertEqual(zero_inv.status, Invoice.Status.PAID)

        non_zero_inv = self._create_invoice(total=Decimal("50.00"), amount_paid=Decimal("0.00"))
        with self.assertRaises(ValidationError):
            mark_zero_total_invoice_paid(non_zero_inv.id)


class RecordPaymentConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="concurrent_cust@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )
        self.staff_user = User.objects.create_user(
            email="concurrent_staff@example.com",
            password="testpassword123",
            role=User.Role.STAFF,
        )
        self.invoice = Invoice.objects.create(
            customer=self.customer,
            subscription_id=20,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 15),
            status=Invoice.Status.CONFIRMED,
            total=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
        )

    def test_two_payments_cannot_both_exceed_outstanding(self):
        """
        Two concurrent payments of 60.00 each against an outstanding balance of 100.00:
        threading.Barrier(2) ensures both threads invoke record_payment at the same moment.
        Row locking ensures exactly one succeeds and the other is rejected with ValidationError,
        preventing overpayment.
        """
        import threading
        from django.db import connection
        from apps.payments.services import record_payment

        results = {}
        barrier = threading.Barrier(2)

        def attempt_payment(thread_idx):
            try:
                barrier.wait(timeout=5.0)
                payment = record_payment(
                    customer_id=self.customer.id,
                    method=Payment.Method.CARD,
                    amount=Decimal("60.00"),
                    allocations=[{"invoice_id": self.invoice.id, "amount": Decimal("60.00")}],
                    recorded_by=self.staff_user,
                )
                results[thread_idx] = ("success", payment)
            except Exception as e:
                results[thread_idx] = ("error", e)
            finally:
                connection.close()

        t1 = threading.Thread(target=attempt_payment, args=(1,))
        t2 = threading.Thread(target=attempt_payment, args=(2,))

        t1.start()
        t2.start()
        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        self.assertEqual(len(results), 2)
        statuses = [res[0] for res in results.values()]
        self.assertEqual(statuses.count("success"), 1)
        self.assertEqual(statuses.count("error"), 1)

        error_entry = [res[1] for res in results.values() if res[0] == "error"][0]
        self.assertIsInstance(error_entry, ValidationError)

        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(PaymentAllocation.objects.count(), 1)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal("60.00"))
        self.assertEqual(self.invoice.status, Invoice.Status.CONFIRMED)

    def test_held_lock_blocks_second_payment_until_commit_then_fails(self):
        """
        Thread A takes select_for_update on the invoice inside transaction.atomic() and holds it (Event).
        Thread B calls record_payment and must block until A commits; then B sees the updated amount_paid
        and fails with the outstanding-balance ValidationError.
        """
        import threading
        import time
        from django.db import connection, transaction
        from apps.payments.services import record_payment

        a_locked = threading.Event()
        a_can_commit = threading.Event()
        b_finished = threading.Event()
        results_b = {}

        def thread_a_worker():
            try:
                with transaction.atomic():
                    inv = Invoice.objects.select_for_update().get(pk=self.invoice.id)
                    inv.amount_paid = Decimal("60.00")
                    inv.save(update_fields=["amount_paid", "updated_at"])
                    a_locked.set()
                    a_can_commit.wait(timeout=5.0)
            finally:
                connection.close()

        def thread_b_worker():
            try:
                a_locked.wait(timeout=5.0)
                record_payment(
                    customer_id=self.customer.id,
                    method=Payment.Method.CARD,
                    amount=Decimal("60.00"),
                    allocations=[{"invoice_id": self.invoice.id, "amount": Decimal("60.00")}],
                    recorded_by=self.staff_user,
                )
                results_b["status"] = "success"
            except Exception as e:
                results_b["status"] = "error"
                results_b["error"] = e
            finally:
                b_finished.set()
                connection.close()

        t_a = threading.Thread(target=thread_a_worker)
        t_b = threading.Thread(target=thread_b_worker)

        t_a.start()
        # Wait until Thread A holds the select_for_update lock
        self.assertTrue(a_locked.wait(timeout=5.0))

        t_b.start()
        # Thread B must be blocked waiting on the lock held by Thread A
        time.sleep(0.2)
        self.assertTrue(t_b.is_alive())
        self.assertFalse(b_finished.is_set())

        # Allow Thread A to commit
        a_can_commit.set()
        t_a.join(timeout=5.0)

        # Thread B unblocks after Thread A commits and fails with ValidationError
        t_b.join(timeout=5.0)
        self.assertTrue(b_finished.is_set())

        self.assertEqual(results_b.get("status"), "error")
        self.assertIsInstance(results_b.get("error"), ValidationError)
        self.assertIn("exceeds outstanding balance", str(results_b.get("error")))

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal("60.00"))
        self.assertEqual(self.invoice.status, Invoice.Status.CONFIRMED)


class BillingAndPaymentsSelectorsTests(TestCase):
    def setUp(self):
        self.customer1 = User.objects.create_user(
            email="sel_cust1@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )
        self.customer2 = User.objects.create_user(
            email="sel_cust2@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )
        self.staff_user = User.objects.create_user(
            email="sel_staff@example.com",
            password="testpassword123",
            role=User.Role.STAFF,
        )

        # Overdue invoice (due 2026-02-01 < 2026-02-15)
        self.inv1 = Invoice.objects.create(
            customer=self.customer1,
            subscription_id=1,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1),
            status=Invoice.Status.CONFIRMED,
            total=Decimal("100.00"),
            amount_paid=Decimal("20.00"),  # outstanding = 80.00
        )
        # Due today boundary invoice (due 2026-02-15 == 2026-02-15 -> NOT overdue)
        self.inv2 = Invoice.objects.create(
            customer=self.customer1,
            subscription_id=2,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 15),
            status=Invoice.Status.CONFIRMED,
            total=Decimal("200.00"),
            amount_paid=Decimal("50.00"),  # outstanding = 150.00
        )
        # Future confirmed invoice (due 2026-02-28)
        self.inv3 = Invoice.objects.create(
            customer=self.customer1,
            subscription_id=3,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 28),
            status=Invoice.Status.CONFIRMED,
            total=Decimal("300.00"),
            amount_paid=Decimal("0.00"),  # outstanding = 300.00
        )
        # Draft invoice
        self.inv_draft = Invoice.objects.create(
            customer=self.customer1,
            subscription_id=4,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1),
            status=Invoice.Status.DRAFT,
            total=Decimal("50.00"),
            amount_paid=Decimal("0.00"),
        )
        # Paid invoice
        self.inv_paid = Invoice.objects.create(
            customer=self.customer1,
            subscription_id=5,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1),
            status=Invoice.Status.PAID,
            total=Decimal("80.00"),
            amount_paid=Decimal("80.00"),
        )
        # Cancelled invoice
        self.inv_cancelled = Invoice.objects.create(
            customer=self.customer1,
            subscription_id=6,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1),
            status=Invoice.Status.CANCELLED,
            total=Decimal("70.00"),
            amount_paid=Decimal("0.00"),
        )

        # Invoice for customer 2 (confirmed, overdue as of 2026-02-15)
        self.inv_cust2 = Invoice.objects.create(
            customer=self.customer2,
            subscription_id=7,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1),
            status=Invoice.Status.CONFIRMED,
            total=Decimal("150.00"),
            amount_paid=Decimal("0.00"),  # outstanding = 150.00
        )

        # Payments and Allocations
        # Payment 1 on 2026-02-10: 20.00 to inv1
        self.pay1 = Payment.objects.create(
            customer=self.customer1,
            method=Payment.Method.CARD,
            amount=Decimal("20.00"),
            payment_date=date(2026, 2, 10),
            recorded_by=self.staff_user,
        )
        PaymentAllocation.objects.create(payment=self.pay1, invoice=self.inv1, amount=Decimal("20.00"))

        # Payment 2 on 2026-02-15 (upper boundary): 50.00 to inv2
        self.pay2 = Payment.objects.create(
            customer=self.customer1,
            method=Payment.Method.UPI,
            amount=Decimal("50.00"),
            payment_date=date(2026, 2, 15),
            recorded_by=self.staff_user,
        )
        PaymentAllocation.objects.create(payment=self.pay2, invoice=self.inv2, amount=Decimal("50.00"))

        # Payment 3 on 2026-02-10: 80.00 to paid invoice
        self.pay3 = Payment.objects.create(
            customer=self.customer1,
            method=Payment.Method.BANK_TRANSFER,
            amount=Decimal("80.00"),
            payment_date=date(2026, 2, 10),
            recorded_by=self.staff_user,
        )
        PaymentAllocation.objects.create(payment=self.pay3, invoice=self.inv_paid, amount=Decimal("80.00"))

        # Payment 4 on 2026-02-10: 30.00 to cancelled invoice
        self.pay4 = Payment.objects.create(
            customer=self.customer1,
            method=Payment.Method.CASH,
            amount=Decimal("30.00"),
            payment_date=date(2026, 2, 10),
            recorded_by=self.staff_user,
        )
        PaymentAllocation.objects.create(payment=self.pay4, invoice=self.inv_cancelled, amount=Decimal("30.00"))

        # Payment 5 on 2026-02-05 (outside range, before start): 10.00
        self.pay5 = Payment.objects.create(
            customer=self.customer1,
            method=Payment.Method.CARD,
            amount=Decimal("10.00"),
            payment_date=date(2026, 2, 5),
            recorded_by=self.staff_user,
        )
        PaymentAllocation.objects.create(payment=self.pay5, invoice=self.inv1, amount=Decimal("10.00"))

        # Payment 6 on 2026-02-20 (outside range, after end): 15.00
        self.pay6 = Payment.objects.create(
            customer=self.customer1,
            method=Payment.Method.CARD,
            amount=Decimal("15.00"),
            payment_date=date(2026, 2, 20),
            recorded_by=self.staff_user,
        )
        PaymentAllocation.objects.create(payment=self.pay6, invoice=self.inv1, amount=Decimal("15.00"))

    def test_billing_outstanding_total(self):
        from apps.billing.selectors import outstanding_total

        # Confirmed invoices:
        # inv1: 100 - 20 = 80
        # inv2: 200 - 50 = 150
        # inv3: 300 - 0 = 300
        # inv_cust2: 150 - 0 = 150
        # Total = 80 + 150 + 300 + 150 = 680.00
        self.assertEqual(outstanding_total(), Decimal("680.00"))

        # With customer filter
        self.assertEqual(
            outstanding_total(filters={"customer_id": self.customer1.id}),
            Decimal("530.00"),
        )
        self.assertEqual(
            outstanding_total(filters={"customer_id": self.customer2.id}),
            Decimal("150.00"),
        )

        # With due date filter
        self.assertEqual(
            outstanding_total(filters={"due_date_to": date(2026, 2, 1)}),
            Decimal("230.00"),
        )

    def test_billing_overdue_invoices_and_total_boundary(self):
        from apps.billing.selectors import overdue_invoices, overdue_total

        as_of = date(2026, 2, 15)
        # inv1: due 2026-02-01 < 2026-02-15 -> OVERDUE (outstanding 80)
        # inv2: due 2026-02-15 == 2026-02-15 -> NOT overdue (due today is NOT overdue)
        # inv3: due 2026-02-28 > 2026-02-15 -> NOT overdue
        # inv_cust2: due 2026-02-01 < 2026-02-15 -> OVERDUE (outstanding 150)
        overdue_qs = overdue_invoices(as_of=as_of)
        overdue_ids = set(overdue_qs.values_list("id", flat=True))
        self.assertEqual(overdue_ids, {self.inv1.id, self.inv_cust2.id})
        self.assertNotIn(self.inv2.id, overdue_ids)

        self.assertEqual(overdue_total(as_of=as_of), Decimal("230.00"))

        # Customer filter
        cust1_overdue = overdue_invoices(as_of=as_of, filters={"customer_id": self.customer1.id})
        self.assertEqual(set(cust1_overdue.values_list("id", flat=True)), {self.inv1.id})
        self.assertEqual(
            overdue_total(as_of=as_of, filters={"customer_id": self.customer1.id}),
            Decimal("80.00"),
        )

    def test_billing_invoice_counts_by_status(self):
        from apps.billing.selectors import invoice_counts_by_status

        counts = invoice_counts_by_status()
        self.assertEqual(
            counts,
            {
                "draft": 1,
                "confirmed": 4,
                "paid": 1,
                "cancelled": 1,
            },
        )

        counts_cust1 = invoice_counts_by_status(filters={"customer_id": self.customer1.id})
        self.assertEqual(
            counts_cust1,
            {
                "draft": 1,
                "confirmed": 3,
                "paid": 1,
                "cancelled": 1,
            },
        )

    def test_payments_revenue_between(self):
        from apps.payments.selectors import revenue_between

        # Start 2026-02-10, End 2026-02-15 (inclusive):
        # pay1: 2026-02-10, alloc 20.00 (inv1, confirmed) -> included
        # pay2: 2026-02-15, alloc 50.00 (inv2, confirmed) -> included (upper boundary inclusive)
        # pay3: 2026-02-10, alloc 80.00 (inv_paid, paid) -> included
        # pay4: 2026-02-10, alloc 30.00 (inv_cancelled, cancelled) -> EXCLUDED
        # pay5: 2026-02-05 -> EXCLUDED (before start)
        # pay6: 2026-02-20 -> EXCLUDED (after end)
        # Total = 20 + 50 + 80 = 150.00
        rev = revenue_between(start=date(2026, 2, 10), end=date(2026, 2, 15))
        self.assertEqual(rev, Decimal("150.00"))

        # Exact day boundary check:
        rev_single_day = revenue_between(start=date(2026, 2, 10), end=date(2026, 2, 10))
        # pay1 (20) + pay3 (80) = 100.00 (cancelled excluded)
        self.assertEqual(rev_single_day, Decimal("100.00"))

        # Customer filter
        rev_cust2 = revenue_between(
            start=date(2026, 2, 10),
            end=date(2026, 2, 15),
            filters={"customer_id": self.customer2.id},
        )
        self.assertEqual(rev_cust2, Decimal("0.00"))

    def test_selectors_query_counts_are_constant(self):
        """
        assertNumQueries showing each selector uses a constant number of queries (1 query)
        regardless of row count.
        """
        from apps.billing.selectors import (
            invoice_counts_by_status,
            outstanding_total,
            overdue_invoices,
            overdue_total,
        )
        from apps.payments.selectors import revenue_between

        as_of = date(2026, 2, 15)
        start = date(2026, 2, 10)
        end = date(2026, 2, 15)

        # Baseline query counts (with existing rows)
        with self.assertNumQueries(1):
            outstanding_total()

        with self.assertNumQueries(1):
            overdue_total(as_of=as_of)

        with self.assertNumQueries(1):
            list(overdue_invoices(as_of=as_of))

        with self.assertNumQueries(1):
            invoice_counts_by_status()

        with self.assertNumQueries(1):
            revenue_between(start=start, end=end)

        # Add 10 more invoices and payments
        for i in range(10):
            inv = Invoice.objects.create(
                customer=self.customer1,
                subscription_id=100 + i,
                period_start=date(2026, 1, 1),
                period_end=date(2026, 1, 31),
                issue_date=date(2026, 1, 1),
                due_date=date(2026, 2, 1),
                status=Invoice.Status.CONFIRMED,
                total=Decimal("100.00"),
                amount_paid=Decimal("10.00"),
            )
            pay = Payment.objects.create(
                customer=self.customer1,
                method=Payment.Method.CARD,
                amount=Decimal("10.00"),
                payment_date=date(2026, 2, 12),
                recorded_by=self.staff_user,
            )
            PaymentAllocation.objects.create(
                payment=pay,
                invoice=inv,
                amount=Decimal("10.00"),
            )

        # Query counts must STILL be exactly 1 query each
        with self.assertNumQueries(1):
            outstanding_total()

        with self.assertNumQueries(1):
            overdue_total(as_of=as_of)

        with self.assertNumQueries(1):
            list(overdue_invoices(as_of=as_of))

        with self.assertNumQueries(1):
            invoice_counts_by_status()

        with self.assertNumQueries(1):
            revenue_between(start=start, end=end)



class RecordPaymentValidationAndZeroTotalTests(TransactionTestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="val_cust@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )
        self.staff_user = User.objects.create_user(
            email="val_staff@example.com",
            password="testpassword123",
            role=User.Role.STAFF,
        )
        self.invoice = Invoice.objects.create(
            customer=self.customer,
            subscription_id=888,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 15),
            status=Invoice.Status.CONFIRMED,
            total=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
        )

    def test_missing_recorded_by_rejected(self):
        """recorded_by is REQUIRED. If None, raise ValidationError({"recorded_by": ...})."""
        from apps.payments.services import record_payment

        with self.assertRaises(ValidationError) as ctx:
            record_payment(
                customer_id=self.customer.id,
                method=Payment.Method.CARD,
                amount=Decimal("50.00"),
                allocations=[{"invoice_id": self.invoice.id, "amount": Decimal("50.00")}],
                recorded_by=None,
            )
        self.assertIn("recorded_by", ctx.exception.message_dict)

        # Confirm that passing integer ID works
        payment = record_payment(
            customer_id=self.customer.id,
            method=Payment.Method.CARD,
            amount=Decimal("50.00"),
            allocations=[{"invoice_id": self.invoice.id, "amount": Decimal("50.00")}],
            recorded_by=self.staff_user.id,
        )
        self.assertEqual(payment.recorded_by_id, self.staff_user.id)

    def test_string_invoice_id_works_and_duplicate_rejected(self):
        """string invoice_id '5' works and '5' plus 5 is rejected as duplicate."""
        from apps.payments.services import record_payment

        # 1. String invoice_id alone works
        payment = record_payment(
            customer_id=self.customer.id,
            method=Payment.Method.CARD,
            amount=Decimal("40.00"),
            allocations=[{"invoice_id": str(self.invoice.id), "amount": Decimal("40.00")}],
            recorded_by=self.staff_user,
        )
        self.assertEqual(payment.allocations.first().invoice_id, self.invoice.id)

        # 2. String invoice_id combined with integer invoice_id rejected as duplicate
        with self.assertRaises(ValidationError) as ctx:
            record_payment(
                customer_id=self.customer.id,
                method=Payment.Method.CARD,
                amount=Decimal("40.00"),
                allocations=[
                    {"invoice_id": str(self.invoice.id), "amount": Decimal("20.00")},
                    {"invoice_id": self.invoice.id, "amount": Decimal("20.00")},
                ],
                recorded_by=self.staff_user,
            )
        self.assertIn("allocations", ctx.exception.message_dict)
        self.assertIn("Duplicate invoice_id", str(ctx.exception))

    def test_invalid_amount_strings_rejected_with_validation_error(self):
        """'abc', 'NaN', 'Infinity' and '0.004' rejected with ValidationError (not an exception)."""
        from apps.payments.services import record_payment

        invalid_values = ["abc", "NaN", "Infinity", "0.004"]

        for val in invalid_values:
            # Rejection on payment amount
            with self.assertRaises(ValidationError, msg=f"Payment amount '{val}' should raise ValidationError"):
                record_payment(
                    customer_id=self.customer.id,
                    method=Payment.Method.CARD,
                    amount=val,
                    allocations=[{"invoice_id": self.invoice.id, "amount": Decimal("10.00")}],
                    recorded_by=self.staff_user,
                )

            # Rejection on allocation amount
            with self.assertRaises(ValidationError, msg=f"Allocation amount '{val}' should raise ValidationError"):
                record_payment(
                    customer_id=self.customer.id,
                    method=Payment.Method.CARD,
                    amount=Decimal("10.00"),
                    allocations=[{"invoice_id": self.invoice.id, "amount": val}],
                    recorded_by=self.staff_user,
                )

    def test_zero_total_helper_rejects_draft_and_cancelled_invoices(self):
        """zero-total helper rejects draft and cancelled invoices."""
        from apps.payments.services import mark_zero_total_invoice_paid

        # Draft zero-total invoice
        draft_inv = Invoice.objects.create(
            customer=self.customer,
            subscription_id=889,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 15),
            status=Invoice.Status.DRAFT,
            total=Decimal("0.00"),
            amount_paid=Decimal("0.00"),
        )
        with self.assertRaises(ValidationError):
            mark_zero_total_invoice_paid(draft_inv.id)
        draft_inv.refresh_from_db()
        self.assertEqual(draft_inv.status, Invoice.Status.DRAFT)

        # Cancelled zero-total invoice
        cancelled_inv = Invoice.objects.create(
            customer=self.customer,
            subscription_id=890,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 15),
            status=Invoice.Status.CANCELLED,
            total=Decimal("0.00"),
            amount_paid=Decimal("0.00"),
        )
        with self.assertRaises(ValidationError):
            mark_zero_total_invoice_paid(cancelled_inv.id)
        cancelled_inv.refresh_from_db()
        self.assertEqual(cancelled_inv.status, Invoice.Status.CANCELLED)

        # Confirmed zero-total invoice should succeed
        confirmed_inv = Invoice.objects.create(
            customer=self.customer,
            subscription_id=891,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 15),
            status=Invoice.Status.CONFIRMED,
            total=Decimal("0.00"),
            amount_paid=Decimal("0.00"),
        )
        paid_inv = mark_zero_total_invoice_paid(confirmed_inv.id)
        confirmed_inv.refresh_from_db()
        self.assertEqual(confirmed_inv.status, Invoice.Status.PAID)
        self.assertEqual(paid_inv.status, Invoice.Status.PAID)

    def test_customer_id_string_works_and_invalid_rejected(self):
        """customer_id '3'-style string works; invalid types rejected with ValidationError."""
        from apps.payments.services import record_payment

        # String customer_id works
        payment = record_payment(
            customer_id=str(self.customer.id),
            method=Payment.Method.CARD,
            amount=Decimal("25.00"),
            allocations=[{"invoice_id": self.invoice.id, "amount": Decimal("25.00")}],
            recorded_by=self.staff_user,
        )
        self.assertEqual(payment.customer_id, self.customer.id)

        # Invalid customer_id types rejected
        invalid_customers = [True, 3.5, "not_an_id", None]
        for bad_id in invalid_customers:
            with self.assertRaises(ValidationError, msg=f"customer_id '{bad_id}' should raise ValidationError") as ctx:
                record_payment(
                    customer_id=bad_id,
                    method=Payment.Method.CARD,
                    amount=Decimal("10.00"),
                    allocations=[{"invoice_id": self.invoice.id, "amount": Decimal("10.00")}],
                    recorded_by=self.staff_user,
                )
            self.assertIn("customer_id", ctx.exception.message_dict)

    def test_huge_amount_and_trailing_zeros(self):
        """huge amount ('1e30') raises ValidationError; trailing zeros like '1.500' accepted."""
        from apps.payments.services import record_payment

        # Huge amount raises ValidationError
        with self.assertRaises(ValidationError, msg="Huge amount '1e30' must raise ValidationError"):
            record_payment(
                customer_id=self.customer.id,
                method=Payment.Method.CARD,
                amount="1e30",
                allocations=[{"invoice_id": self.invoice.id, "amount": "1e30"}],
                recorded_by=self.staff_user,
            )

        # Trailing zeros accepted
        payment = record_payment(
            customer_id=self.customer.id,
            method=Payment.Method.CARD,
            amount="1.500",
            allocations=[{"invoice_id": self.invoice.id, "amount": "1.500"}],
            recorded_by=self.staff_user,
        )
        self.assertEqual(payment.amount, Decimal("1.50"))
        self.assertEqual(payment.allocations.first().amount, Decimal("1.50"))

    def test_zero_total_helper_nonexistent_invoice_raises_validation_error(self):
        """zero-total helper with nonexistent id raises ValidationError."""
        from apps.payments.services import mark_zero_total_invoice_paid

        with self.assertRaises(ValidationError):
            mark_zero_total_invoice_paid(999999)

