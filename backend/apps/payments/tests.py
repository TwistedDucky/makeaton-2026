from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase
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
            PaymentAllocation.objects.create(
                payment=payment,
                invoice=self.invoice,
                amount=Decimal("-50.00"),
            )
