"""
API tests for the payments app.
Covers customer isolation, staff permissions, filtering, ordering,
recording payments, validation errors, CSRF enforcement, query counts, and disallowed methods.
"""
from datetime import date, timedelta
from decimal import Decimal
import json

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from .models import Payment, PaymentAllocation

User = get_user_model()


class PaymentsAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_user(
            email="admin_pay_api@example.com",
            password="testpassword123",
            role=User.Role.ADMIN,
        )
        cls.staff_user = User.objects.create_user(
            email="staff_pay_api@example.com",
            password="testpassword123",
            role=User.Role.STAFF,
        )
        cls.customer1 = User.objects.create_user(
            email="cust1_pay_api@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )
        cls.customer2 = User.objects.create_user(
            email="cust2_pay_api@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )

    def setUp(self):
        self.client = APIClient()
        self.today = timezone.localdate()

    _sub_counter = 2000

    def _create_invoice(
        self,
        customer,
        status="confirmed",
        total=Decimal("100.00"),
        amount_paid=Decimal("0.00"),
        due_date=None,
        issue_date=None,
        number=None,
    ):
        from apps.billing.models import Invoice

        if due_date is None:
            due_date = self.today + timedelta(days=14)
        if issue_date is None:
            issue_date = due_date - timedelta(days=14)
        PaymentsAPITests._sub_counter += 1
        sub_id = PaymentsAPITests._sub_counter
        return Invoice.objects.create(
            customer=customer,
            status=status,
            subtotal=total,
            discount_total=Decimal("0.00"),
            tax_total=Decimal("0.00"),
            total=total,
            amount_paid=amount_paid,
            due_date=due_date,
            issue_date=issue_date,
            period_start=issue_date,
            period_end=issue_date + timedelta(days=30),
            number=number,
            subscription_id=sub_id,
        )

    # -------------------------------------------------------------------------
    # 1. Customer list/detail own only; other's detail 404; customer filter ignored
    # -------------------------------------------------------------------------
    def test_customer_list_and_detail_scoping(self):
        """Customer sees only own payments; other customer's payment detail returns 404; customer filter ignored."""
        inv1 = self._create_invoice(self.customer1, number="INV-PAY-C1")
        inv2 = self._create_invoice(self.customer2, number="INV-PAY-C2")

        pay1 = Payment.objects.create(
            customer=self.customer1,
            method=Payment.Method.CARD,
            amount=Decimal("50.00"),
            payment_date=self.today,
            recorded_by=self.staff_user,
            note="Payment 1",
        )
        PaymentAllocation.objects.create(
            payment=pay1, invoice=inv1, amount=Decimal("50.00")
        )

        pay2 = Payment.objects.create(
            customer=self.customer2,
            method=Payment.Method.UPI,
            amount=Decimal("75.00"),
            payment_date=self.today,
            recorded_by=self.staff_user,
            note="Payment 2",
        )
        PaymentAllocation.objects.create(
            payment=pay2, invoice=inv2, amount=Decimal("75.00")
        )

        self.client.force_authenticate(user=self.customer1)

        # List shows only customer1's payment
        resp = self.client.get("/api/payments/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in resp.data["results"]]
        self.assertIn(pay1.id, ids)
        self.assertNotIn(pay2.id, ids)

        # Detail own -> 200
        resp_own = self.client.get(f"/api/payments/{pay1.id}/")
        self.assertEqual(resp_own.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_own.data["id"], pay1.id)
        self.assertEqual(resp_own.data["customer"]["email"], self.customer1.email)

        # Detail other -> 404
        resp_other = self.client.get(f"/api/payments/{pay2.id}/")
        self.assertEqual(resp_other.status_code, status.HTTP_404_NOT_FOUND)

        # Customer filter ignored for customers
        resp_filter = self.client.get(f"/api/payments/?customer={self.customer2.id}")
        self.assertEqual(resp_filter.status_code, status.HTTP_200_OK)
        filtered_ids = [item["id"] for item in resp_filter.data["results"]]
        self.assertIn(pay1.id, filtered_ids)
        self.assertNotIn(pay2.id, filtered_ids)

    # -------------------------------------------------------------------------
    # 2. Customer POST -> 403 (before validation, even with empty body); unauthenticated -> 403
    # -------------------------------------------------------------------------
    def test_customer_post_forbidden_and_unauthenticated(self):
        """Customer POST returns 403 before body validation (even with empty body); unauthenticated returns 403."""
        self.client.force_authenticate(user=self.customer1)

        # Empty body -> 403
        resp_empty = self.client.post("/api/payments/", {}, format="json")
        self.assertEqual(resp_empty.status_code, status.HTTP_403_FORBIDDEN)

        # Valid-shaped body from customer -> 403
        resp_body = self.client.post(
            "/api/payments/",
            {
                "customer": self.customer1.id,
                "method": "card",
                "amount": "50.00",
                "allocations": [{"invoice": 1, "amount": "50.00"}],
            },
            format="json",
        )
        self.assertEqual(resp_body.status_code, status.HTTP_403_FORBIDDEN)

        # Unauthenticated request -> 403
        self.client.logout()
        resp_unauth_get = self.client.get("/api/payments/")
        self.assertEqual(resp_unauth_get.status_code, status.HTTP_403_FORBIDDEN)

        resp_unauth_post = self.client.post("/api/payments/", {}, format="json")
        self.assertEqual(resp_unauth_post.status_code, status.HTTP_403_FORBIDDEN)

    # -------------------------------------------------------------------------
    # 3. Staff list filters, ordering, default order, pagination shape; bad method/date -> 400
    # -------------------------------------------------------------------------
    def test_staff_list_filters_and_ordering(self):
        """Staff list supports filters (customer, method, date_from/to, invoice id/number), ordering, pagination; bad values -> 400."""
        inv1 = self._create_invoice(self.customer1, number="INV-FILTER-001")
        inv2 = self._create_invoice(self.customer2, number="INV-FILTER-002")

        pay1 = Payment.objects.create(
            customer=self.customer1,
            method=Payment.Method.CARD,
            amount=Decimal("100.00"),
            payment_date=self.today - timedelta(days=5),
            recorded_by=self.staff_user,
            note="Staff pay 1",
        )
        PaymentAllocation.objects.create(
            payment=pay1, invoice=inv1, amount=Decimal("100.00")
        )

        pay2 = Payment.objects.create(
            customer=self.customer2,
            method=Payment.Method.BANK_TRANSFER,
            amount=Decimal("200.00"),
            payment_date=self.today - timedelta(days=2),
            recorded_by=self.staff_user,
            note="Staff pay 2",
        )
        PaymentAllocation.objects.create(
            payment=pay2, invoice=inv2, amount=Decimal("200.00")
        )

        self.client.force_authenticate(user=self.staff_user)

        # Pagination envelope shape
        resp_all = self.client.get("/api/payments/")
        self.assertEqual(resp_all.status_code, status.HTTP_200_OK)
        self.assertIn("count", resp_all.data)
        self.assertIn("next", resp_all.data)
        self.assertIn("previous", resp_all.data)
        self.assertIn("results", resp_all.data)

        # Filter by customer
        resp_cust = self.client.get(f"/api/payments/?customer={self.customer2.id}")
        self.assertEqual(resp_cust.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_cust.data["results"]), 1)
        self.assertEqual(resp_cust.data["results"][0]["id"], pay2.id)

        # Filter by method
        resp_method = self.client.get("/api/payments/?method=card")
        self.assertEqual(resp_method.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_method.data["results"]), 1)
        self.assertEqual(resp_method.data["results"][0]["id"], pay1.id)

        # Filter by date_from and date_to
        d_from = (self.today - timedelta(days=3)).isoformat()
        d_to = self.today.isoformat()
        resp_date = self.client.get(f"/api/payments/?date_from={d_from}&date_to={d_to}")
        self.assertEqual(resp_date.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_date.data["results"]), 1)
        self.assertEqual(resp_date.data["results"][0]["id"], pay2.id)

        # Filter by invoice ID
        resp_inv_id = self.client.get(f"/api/payments/?invoice={inv1.id}")
        self.assertEqual(resp_inv_id.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_inv_id.data["results"]), 1)
        self.assertEqual(resp_inv_id.data["results"][0]["id"], pay1.id)

        # Filter by invoice number
        resp_inv_num = self.client.get("/api/payments/?invoice=INV-FILTER-002")
        self.assertEqual(resp_inv_num.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_inv_num.data["results"]), 1)
        self.assertEqual(resp_inv_num.data["results"][0]["id"], pay2.id)

        # Ordering by amount ascending
        resp_asc = self.client.get("/api/payments/?ordering=amount")
        self.assertEqual(resp_asc.status_code, status.HTTP_200_OK)
        amounts = [Decimal(p["amount"]) for p in resp_asc.data["results"] if p["id"] in [pay1.id, pay2.id]]
        self.assertEqual(amounts, sorted(amounts))

        # Default ordering: -payment_date
        resp_def = self.client.get("/api/payments/")
        dates = [p["payment_date"] for p in resp_def.data["results"] if p["id"] in [pay1.id, pay2.id]]
        self.assertEqual(dates, sorted(dates, reverse=True))

        # Bad method -> 400
        resp_bad_method = self.client.get("/api/payments/?method=bitcoin")
        self.assertEqual(resp_bad_method.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(resp_bad_method.data["success"])

        # Bad date_from -> 400
        resp_bad_date = self.client.get("/api/payments/?date_from=not-a-date")
        self.assertEqual(resp_bad_date.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(resp_bad_date.data["success"])

    # -------------------------------------------------------------------------
    # 4. POST: full payment marks invoice paid; partial leaves confirmed; multi-invoice split; invoice by number and id
    # -------------------------------------------------------------------------
    def test_post_payment_lifecycle_and_multi_invoice_split(self):
        """Full payment marks paid, partial leaves confirmed, multi-invoice split works by id and number; 201 response."""
        from apps.billing.models import Invoice

        self.client.force_authenticate(user=self.staff_user)

        # A. Full payment marks invoice PAID
        inv_full = self._create_invoice(
            self.customer1, status=Invoice.Status.CONFIRMED, total=Decimal("100.00")
        )
        resp_full = self.client.post(
            "/api/payments/",
            {
                "customer": self.customer1.id,
                "method": "card",
                "amount": "100.00",
                "payment_date": self.today.isoformat(),
                "note": "Full payment test",
                "allocations": [{"invoice": inv_full.id, "amount": "100.00"}],
            },
            format="json",
        )
        self.assertEqual(resp_full.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp_full.data["success"])
        self.assertEqual(resp_full.data["data"]["amount"], "100.00")
        self.assertIsInstance(resp_full.data["data"]["amount"], str)
        inv_full.refresh_from_db()
        self.assertEqual(inv_full.status, Invoice.Status.PAID)
        self.assertEqual(inv_full.amount_paid, Decimal("100.00"))

        # B. Partial payment leaves invoice CONFIRMED
        inv_part = self._create_invoice(
            self.customer1, status=Invoice.Status.CONFIRMED, total=Decimal("100.00")
        )
        resp_part = self.client.post(
            "/api/payments/",
            {
                "customer": self.customer1.id,
                "method": "upi",
                "amount": "40.00",
                "payment_date": self.today.isoformat(),
                "note": "Partial payment test",
                "allocations": [{"invoice": inv_part.id, "amount": "40.00"}],
            },
            format="json",
        )
        self.assertEqual(resp_part.status_code, status.HTTP_201_CREATED)
        inv_part.refresh_from_db()
        self.assertEqual(inv_part.status, Invoice.Status.CONFIRMED)
        self.assertEqual(inv_part.amount_paid, Decimal("40.00"))

        # C. Multi-invoice split: one by id, one by number
        inv_split1 = self._create_invoice(
            self.customer1, status=Invoice.Status.CONFIRMED, total=Decimal("60.00"), number="INV-SPLIT-01"
        )
        inv_split2 = self._create_invoice(
            self.customer1, status=Invoice.Status.CONFIRMED, total=Decimal("40.00"), number="INV-SPLIT-02"
        )
        resp_split = self.client.post(
            "/api/payments/",
            {
                "customer": self.customer1.id,
                "method": "bank_transfer",
                "amount": "100.00",
                "payment_date": self.today.isoformat(),
                "note": "Multi-split test",
                "allocations": [
                    {"invoice": inv_split1.id, "amount": "60.00"},
                    {"invoice": "INV-SPLIT-02", "amount": "40.00"},
                ],
            },
            format="json",
        )
        self.assertEqual(resp_split.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(resp_split.data["data"]["allocations"]), 2)
        alloc_map = {a["invoice_number"]: a["amount"] for a in resp_split.data["data"]["allocations"]}
        self.assertEqual(alloc_map.get("INV-SPLIT-01"), "60.00")
        self.assertEqual(alloc_map.get("INV-SPLIT-02"), "40.00")
        inv_split1.refresh_from_db()
        inv_split2.refresh_from_db()
        self.assertEqual(inv_split1.status, Invoice.Status.PAID)
        self.assertEqual(inv_split2.status, Invoice.Status.PAID)

    # -------------------------------------------------------------------------
    # 5. POST errors
    # -------------------------------------------------------------------------
    def test_post_payment_validation_errors(self):
        """POST errors: over-payment, wrong customer, draft invoice, unknown invoice, JSON numbers, unknown customer, sum mismatch."""
        from apps.billing.models import Invoice

        self.client.force_authenticate(user=self.staff_user)

        inv_c1 = self._create_invoice(
            self.customer1, status=Invoice.Status.CONFIRMED, total=Decimal("100.00"), number="INV-ERR-001"
        )
        inv_draft = self._create_invoice(
            self.customer1, status=Invoice.Status.DRAFT, total=Decimal("100.00"), number="INV-ERR-DRAFT"
        )

        initial_pay_count = Payment.objects.count()
        initial_alloc_count = PaymentAllocation.objects.count()

        # A. Over-payment (> outstanding balance) -> 400, nothing written
        resp_over = self.client.post(
            "/api/payments/",
            {
                "customer": self.customer1.id,
                "method": "card",
                "amount": "150.00",
                "allocations": [{"invoice": inv_c1.id, "amount": "150.00"}],
            },
            format="json",
        )
        self.assertEqual(resp_over.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Payment.objects.count(), initial_pay_count)
        self.assertEqual(PaymentAllocation.objects.count(), initial_alloc_count)
        inv_c1.refresh_from_db()
        self.assertEqual(inv_c1.amount_paid, Decimal("0.00"))

        # B. Wrong customer (invoice belongs to customer1, payload says customer2) -> 400
        resp_wrong_cust = self.client.post(
            "/api/payments/",
            {
                "customer": self.customer2.id,
                "method": "card",
                "amount": "50.00",
                "allocations": [{"invoice": inv_c1.id, "amount": "50.00"}],
            },
            format="json",
        )
        self.assertEqual(resp_wrong_cust.status_code, status.HTTP_400_BAD_REQUEST)

        # C. Draft invoice -> 400
        resp_draft = self.client.post(
            "/api/payments/",
            {
                "customer": self.customer1.id,
                "method": "card",
                "amount": "50.00",
                "allocations": [{"invoice": inv_draft.id, "amount": "50.00"}],
            },
            format="json",
        )
        self.assertEqual(resp_draft.status_code, status.HTTP_400_BAD_REQUEST)

        # D. Unknown invoice number string -> 400
        resp_unknown_inv = self.client.post(
            "/api/payments/",
            {
                "customer": self.customer1.id,
                "method": "card",
                "amount": "50.00",
                "allocations": [{"invoice": "INV-NONEXISTENT-999", "amount": "50.00"}],
            },
            format="json",
        )
        self.assertEqual(resp_unknown_inv.status_code, status.HTTP_400_BAD_REQUEST)

        # E. JSON-number amount (float) -> 400
        resp_num_amt = self.client.post(
            "/api/payments/",
            {
                "customer": self.customer1.id,
                "method": "card",
                "amount": 50.00,
                "allocations": [{"invoice": inv_c1.id, "amount": "50.00"}],
            },
            format="json",
        )
        self.assertEqual(resp_num_amt.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("must be a string", str(resp_num_amt.data).lower())

        # F. JSON-number allocation amount (float) -> 400
        resp_num_alloc = self.client.post(
            "/api/payments/",
            {
                "customer": self.customer1.id,
                "method": "card",
                "amount": "50.00",
                "allocations": [{"invoice": inv_c1.id, "amount": 50.00}],
            },
            format="json",
        )
        self.assertEqual(resp_num_alloc.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("must be a string", str(resp_num_alloc.data).lower())

        # G. Unknown customer user id -> 400
        resp_unknown_user = self.client.post(
            "/api/payments/",
            {
                "customer": 999999,
                "method": "card",
                "amount": "50.00",
                "allocations": [{"invoice": inv_c1.id, "amount": "50.00"}],
            },
            format="json",
        )
        self.assertEqual(resp_unknown_user.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("does not exist", str(resp_unknown_user.data).lower())

        # H. Allocation sum mismatch -> 400
        resp_mismatch = self.client.post(
            "/api/payments/",
            {
                "customer": self.customer1.id,
                "method": "card",
                "amount": "100.00",
                "allocations": [{"invoice": inv_c1.id, "amount": "80.00"}],
            },
            format="json",
        )
        self.assertEqual(resp_mismatch.status_code, status.HTTP_400_BAD_REQUEST)

    # -------------------------------------------------------------------------
    # 6. CSRF test with APIClient(enforce_csrf_checks=True)
    # -------------------------------------------------------------------------
    def test_csrf_enforcement_on_session_auth(self):
        """APIClient with enforce_csrf_checks=True rejects POST without CSRF token (403)."""
        client = APIClient(enforce_csrf_checks=True)
        client.login(email="staff_pay_api@example.com", password="testpassword123")
        inv = self._create_invoice(self.customer1, status="confirmed")

        # POST without X-CSRFToken -> 403 Forbidden
        resp = client.post(
            "/api/payments/",
            {
                "customer": self.customer1.id,
                "method": "card",
                "amount": "50.00",
                "allocations": [{"invoice": inv.id, "amount": "50.00"}],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # -------------------------------------------------------------------------
    # 7. assertNumQueries: list count identical for 3 and 15 payments; detail constant
    # -------------------------------------------------------------------------
    def test_query_counts_constant(self):
        """List query count is identical for 3 and 15 payments; detail query count is constant."""
        self.client.force_authenticate(user=self.staff_user)

        # Create 3 payments with allocations
        for i in range(3):
            inv = self._create_invoice(self.customer1, number=f"INV-QC-P-{i}")
            p = Payment.objects.create(
                customer=self.customer1,
                method=Payment.Method.CARD,
                amount=Decimal("10.00"),
                payment_date=self.today,
                recorded_by=self.staff_user,
                note=f"QC Pay {i}",
            )
            PaymentAllocation.objects.create(
                payment=p, invoice=inv, amount=Decimal("10.00")
            )

        with self.assertNumQueries(4):
            # 1 count query + 1 select payments with customer & recorded_by + 1 select allocations + 1 select invoices
            resp3 = self.client.get(f"/api/payments/?customer={self.customer1.id}")
            self.assertEqual(resp3.status_code, status.HTTP_200_OK)
            self.assertEqual(len(resp3.data["results"]), 3)

        # Add 12 more payments (total 15)
        for i in range(3, 15):
            inv = self._create_invoice(self.customer1, number=f"INV-QC-P-{i}")
            p = Payment.objects.create(
                customer=self.customer1,
                method=Payment.Method.CARD,
                amount=Decimal("10.00"),
                payment_date=self.today,
                recorded_by=self.staff_user,
                note=f"QC Pay {i}",
            )
            PaymentAllocation.objects.create(
                payment=p, invoice=inv, amount=Decimal("10.00")
            )

        with self.assertNumQueries(4):
            resp15 = self.client.get(f"/api/payments/?customer={self.customer1.id}")
            self.assertEqual(resp15.status_code, status.HTTP_200_OK)
            self.assertEqual(len(resp15.data["results"]), 15)

        # Detail query count: single allocation vs multiple allocations
        p_single = Payment.objects.create(
            customer=self.customer1,
            method=Payment.Method.CARD,
            amount=Decimal("10.00"),
            payment_date=self.today,
            recorded_by=self.staff_user,
            note="Single alloc",
        )
        inv_single = self._create_invoice(self.customer1, number="INV-DET-SINGLE")
        PaymentAllocation.objects.create(
            payment=p_single, invoice=inv_single, amount=Decimal("10.00")
        )

        p_multi = Payment.objects.create(
            customer=self.customer1,
            method=Payment.Method.CARD,
            amount=Decimal("50.00"),
            payment_date=self.today,
            recorded_by=self.staff_user,
            note="Multi alloc",
        )
        for j in range(5):
            inv_j = self._create_invoice(self.customer1, number=f"INV-DET-MULTI-{j}")
            PaymentAllocation.objects.create(
                payment=p_multi, invoice=inv_j, amount=Decimal("10.00")
            )

        with self.assertNumQueries(3):
            # 1 payment with customer & recorded_by + 1 allocations + 1 invoices
            resp_det_single = self.client.get(f"/api/payments/{p_single.id}/")
            self.assertEqual(resp_det_single.status_code, status.HTTP_200_OK)

        with self.assertNumQueries(3):
            resp_det_multi = self.client.get(f"/api/payments/{p_multi.id}/")
            self.assertEqual(resp_det_multi.status_code, status.HTTP_200_OK)

    # -------------------------------------------------------------------------
    # 8. PUT/PATCH/DELETE -> 405
    # -------------------------------------------------------------------------
    def test_disallowed_http_methods_return_405(self):
        """PUT, PATCH, DELETE on payments return 405 Method Not Allowed."""
        self.client.force_authenticate(user=self.staff_user)
        inv = self._create_invoice(self.customer1, status="confirmed")
        p = Payment.objects.create(
            customer=self.customer1,
            method=Payment.Method.CARD,
            amount=Decimal("20.00"),
            payment_date=self.today,
            recorded_by=self.staff_user,
        )
        PaymentAllocation.objects.create(
            payment=p, invoice=inv, amount=Decimal("20.00")
        )

        resp_put_detail = self.client.put(f"/api/payments/{p.id}/", {"amount": "30.00"}, format="json")
        self.assertEqual(resp_put_detail.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        resp_patch_detail = self.client.patch(f"/api/payments/{p.id}/", {"amount": "30.00"}, format="json")
        self.assertEqual(resp_patch_detail.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        resp_delete_detail = self.client.delete(f"/api/payments/{p.id}/")
        self.assertEqual(resp_delete_detail.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        resp_put_list = self.client.put("/api/payments/", {"amount": "30.00"}, format="json")
        self.assertEqual(resp_put_list.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

