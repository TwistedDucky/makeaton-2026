"""
API tests for billing (invoices).
Covers permissions, filtering, ordering, actions, response envelopes,
CSRF enforcement, and query counts.
"""
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from . import integrations
from .models import IllegalStatusTransitionError, Invoice, InvoiceDiscount, InvoiceLine

User = get_user_model()


class FakeSubscriptionsService:
    """Lightweight subscriptions fake for invoice generation API tests."""

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


class BillingAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_user(
            email="admin_api@example.com",
            password="testpassword123",
            role=User.Role.ADMIN,
        )
        cls.staff_user = User.objects.create_user(
            email="staff_api@example.com",
            password="testpassword123",
            role=User.Role.STAFF,
        )
        cls.customer1 = User.objects.create_user(
            email="cust1_api@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )
        cls.customer2 = User.objects.create_user(
            email="cust2_api@example.com",
            password="testpassword123",
            role=User.Role.CUSTOMER,
        )

    def setUp(self):
        self.client = APIClient()
        self.today = timezone.localdate()

    _sub_counter = 1000

    def _create_invoice(
        self,
        customer,
        status=Invoice.Status.DRAFT,
        total=Decimal("100.00"),
        amount_paid=Decimal("0.00"),
        due_date=None,
        issue_date=None,
        period_start=None,
        period_end=None,
        number=None,
        subscription_id=None,
    ):
        if due_date is None:
            due_date = self.today + timedelta(days=14)
        if issue_date is None:
            if due_date < self.today:
                issue_date = due_date - timedelta(days=14)
            else:
                issue_date = self.today
        if period_start is None:
            period_start = issue_date
        if period_end is None:
            period_end = period_start + timedelta(days=30)
        if subscription_id is None:
            BillingAPITests._sub_counter += 1
            subscription_id = BillingAPITests._sub_counter
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
            period_start=period_start,
            period_end=period_end,
            number=number,
            subscription_id=subscription_id,
        )

    # -------------------------------------------------------------------------
    # 1. Customer Scoping & Permissions
    # -------------------------------------------------------------------------
    def test_customer_list_and_detail_scoping(self):
        """Customer list and detail show only own invoices; other customer detail is 404."""
        inv1 = self._create_invoice(self.customer1, number="INV-C1-001")
        inv2 = self._create_invoice(self.customer2, number="INV-C2-001")

        self.client.force_authenticate(user=self.customer1)

        # List
        resp = self.client.get("/api/billing/invoices/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in resp.data["results"]]
        self.assertIn(inv1.id, ids)
        self.assertNotIn(inv2.id, ids)

        # Detail own -> 200
        resp_own = self.client.get(f"/api/billing/invoices/{inv1.id}/")
        self.assertEqual(resp_own.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_own.data["id"], inv1.id)

        # Detail other -> 404
        resp_other = self.client.get(f"/api/billing/invoices/{inv2.id}/")
        self.assertEqual(resp_other.status_code, status.HTTP_404_NOT_FOUND)

        # Customer query filter ignored for customers
        resp_filter = self.client.get(f"/api/billing/invoices/?customer={self.customer2.id}")
        self.assertEqual(resp_filter.status_code, status.HTTP_200_OK)
        filtered_ids = [item["id"] for item in resp_filter.data["results"]]
        self.assertIn(inv1.id, filtered_ids)
        self.assertNotIn(inv2.id, filtered_ids)

        # Customer search by email does not leak others
        resp_search = self.client.get("/api/billing/invoices/?search=cust2_api")
        self.assertEqual(resp_search.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_search.data["results"]), 0)

    # -------------------------------------------------------------------------
    # 2. Customer Action Forbidden (403) and Unauthenticated (403)
    # -------------------------------------------------------------------------
    def test_customer_actions_forbidden_and_unauthenticated(self):
        """Customer gets 403 on confirm, cancel, generate (even for nonexistent id). Unauthenticated -> 403."""
        inv = self._create_invoice(self.customer1, status=Invoice.Status.DRAFT)

        self.client.force_authenticate(user=self.customer1)

        # Customer calls confirm on own invoice -> 403
        resp = self.client.post(f"/api/billing/invoices/{inv.id}/confirm/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # Customer calls cancel on own invoice -> 403
        resp = self.client.post(f"/api/billing/invoices/{inv.id}/cancel/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # Customer calls generate -> 403
        resp = self.client.post("/api/billing/invoices/generate/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # Customer calls confirm on nonexistent id -> 403, NOT 404
        resp = self.client.post("/api/billing/invoices/999999/confirm/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # Unauthenticated request -> 403
        self.client.logout()
        resp_unauth = self.client.get("/api/billing/invoices/")
        self.assertEqual(resp_unauth.status_code, status.HTTP_403_FORBIDDEN)

        resp_unauth_post = self.client.post(f"/api/billing/invoices/{inv.id}/confirm/")
        self.assertEqual(resp_unauth_post.status_code, status.HTTP_403_FORBIDDEN)

    # -------------------------------------------------------------------------
    # 3. Staff List: Filters, Search, Ordering, Pagination
    # -------------------------------------------------------------------------
    def test_staff_list_filters_and_ordering(self):
        """Staff list supports status, customer, date range, overdue, search, ordering, pagination."""
        inv1 = self._create_invoice(
            self.customer1,
            status=Invoice.Status.DRAFT,
            total=Decimal("200.00"),
            due_date=self.today + timedelta(days=5),
            number="INV-STAFF-001",
        )
        inv2 = self._create_invoice(
            self.customer2,
            status=Invoice.Status.CONFIRMED,
            total=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
            due_date=self.today - timedelta(days=2),
            number="INV-STAFF-002",
        )
        inv3 = self._create_invoice(
            self.customer1,
            status=Invoice.Status.PAID,
            total=Decimal("300.00"),
            amount_paid=Decimal("300.00"),
            due_date=self.today + timedelta(days=10),
            number="INV-STAFF-003",
        )

        self.client.force_authenticate(user=self.staff_user)

        # Status filter
        resp = self.client.get("/api/billing/invoices/?status=draft")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["id"], inv1.id)

        # Customer filter
        resp = self.client.get(f"/api/billing/invoices/?customer={self.customer2.id}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["id"], inv2.id)

        # Date range filter
        d_from = (self.today + timedelta(days=4)).isoformat()
        d_to = (self.today + timedelta(days=6)).isoformat()
        resp = self.client.get(f"/api/billing/invoices/?due_date_from={d_from}&due_date_to={d_to}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["id"], inv1.id)

        # Overdue filter (inv2 is confirmed and due 2 days ago with outstanding > 0)
        resp = self.client.get("/api/billing/invoices/?overdue=true")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in resp.data["results"]]
        self.assertIn(inv2.id, ids)
        self.assertNotIn(inv1.id, ids)
        self.assertNotIn(inv3.id, ids)

        # Search by number (case-insensitive partial)
        resp = self.client.get("/api/billing/invoices/?search=staff-003")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["id"], inv3.id)

        # Search by customer email (staff only)
        resp = self.client.get("/api/billing/invoices/?search=cust2_api")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["id"], inv2.id)

        # Ordering: ascending by total
        resp = self.client.get("/api/billing/invoices/?ordering=total")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        totals = [Decimal(i["total"]) for i in resp.data["results"] if i["id"] in [inv1.id, inv2.id, inv3.id]]
        self.assertEqual(totals, sorted(totals))

        # Ordering: descending by total
        resp = self.client.get("/api/billing/invoices/?ordering=-total")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        totals = [Decimal(i["total"]) for i in resp.data["results"] if i["id"] in [inv1.id, inv2.id, inv3.id]]
        self.assertEqual(totals, sorted(totals, reverse=True))

        # Pagination envelope shape
        self.assertIn("count", resp.data)
        self.assertIn("next", resp.data)
        self.assertIn("previous", resp.data)
        self.assertIn("results", resp.data)

        # Bad status format -> 400
        resp_bad = self.client.get("/api/billing/invoices/?status=unknown_status")
        self.assertEqual(resp_bad.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(resp_bad.data["success"])

        # Bad date format -> 400
        resp_bad_date = self.client.get("/api/billing/invoices/?due_date_from=not-a-date")
        self.assertEqual(resp_bad_date.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(resp_bad_date.data["success"])

    # -------------------------------------------------------------------------
    # 4. Outstanding and is_overdue Calculations
    # -------------------------------------------------------------------------
    def test_outstanding_and_is_overdue_computation(self):
        """Test outstanding and is_overdue for due today, yesterday, draft, paid, and partially paid."""
        # Due today confirmed -> not overdue
        inv_today = self._create_invoice(
            self.customer1,
            status=Invoice.Status.CONFIRMED,
            total=Decimal("150.00"),
            due_date=self.today,
        )
        # Due yesterday confirmed -> overdue
        inv_yesterday = self._create_invoice(
            self.customer1,
            status=Invoice.Status.CONFIRMED,
            total=Decimal("150.00"),
            due_date=self.today - timedelta(days=1),
        )
        # Paid invoice -> outstanding 0.00, not overdue
        inv_paid = self._create_invoice(
            self.customer1,
            status=Invoice.Status.PAID,
            total=Decimal("150.00"),
            amount_paid=Decimal("150.00"),
            due_date=self.today - timedelta(days=5),
        )
        # Draft invoice -> outstanding 0.00, not overdue
        inv_draft = self._create_invoice(
            self.customer1,
            status=Invoice.Status.DRAFT,
            total=Decimal("150.00"),
            due_date=self.today - timedelta(days=5),
        )
        # Partially paid confirmed invoice
        inv_part = self._create_invoice(
            self.customer1,
            status=Invoice.Status.CONFIRMED,
            total=Decimal("150.00"),
            amount_paid=Decimal("50.00"),
            due_date=self.today + timedelta(days=5),
        )

        self.client.force_authenticate(user=self.staff_user)

        resp_today = self.client.get(f"/api/billing/invoices/{inv_today.id}/")
        self.assertFalse(resp_today.data["is_overdue"])
        self.assertEqual(resp_today.data["outstanding"], "150.00")

        resp_yesterday = self.client.get(f"/api/billing/invoices/{inv_yesterday.id}/")
        self.assertTrue(resp_yesterday.data["is_overdue"])
        self.assertEqual(resp_yesterday.data["outstanding"], "150.00")

        resp_paid = self.client.get(f"/api/billing/invoices/{inv_paid.id}/")
        self.assertFalse(resp_paid.data["is_overdue"])
        self.assertEqual(resp_paid.data["outstanding"], "0.00")

        resp_draft = self.client.get(f"/api/billing/invoices/{inv_draft.id}/")
        self.assertFalse(resp_draft.data["is_overdue"])
        self.assertEqual(resp_draft.data["outstanding"], "0.00")

        resp_part = self.client.get(f"/api/billing/invoices/{inv_part.id}/")
        self.assertFalse(resp_part.data["is_overdue"])
        self.assertEqual(resp_part.data["outstanding"], "100.00")

    # -------------------------------------------------------------------------
    # 5. Confirm Actions
    # -------------------------------------------------------------------------
    def test_confirm_actions(self):
        """Confirm with no discounts, with discount fallback, non-draft -> 409, 2nd failure -> 400, nonexistent -> 404."""
        self.client.force_authenticate(user=self.staff_user)

        # A. Confirm draft with no discounts
        inv = self._create_invoice(self.customer1, status=Invoice.Status.DRAFT)
        InvoiceLine.objects.create(
            invoice=inv,
            product_name="Product A",
            quantity=1,
            unit_price=Decimal("100.00"),
            line_total=Decimal("100.00"),
        )
        resp = self.client.post(f"/api/billing/invoices/{inv.id}/confirm/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["success"])
        self.assertEqual(resp.data["data"]["invoice"]["status"], Invoice.Status.CONFIRMED)
        self.assertFalse(resp.data["data"]["amounts_changed"])

        # B. Confirm on non-draft -> 409 Conflict
        resp_conflict = self.client.post(f"/api/billing/invoices/{inv.id}/confirm/")
        self.assertEqual(resp_conflict.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(resp_conflict.data["success"])
        self.assertIn("current status is 'confirmed'", resp_conflict.data["message"])

        # C. Nonexistent invoice -> 404
        resp_404 = self.client.post("/api/billing/invoices/999999/confirm/")
        self.assertEqual(resp_404.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(resp_404.data["success"])

        # D. Confirm with discount via mocked redemption returning amounts_changed True
        inv_disc = self._create_invoice(self.customer1, status=Invoice.Status.DRAFT, total=Decimal("80.00"))
        line = InvoiceLine.objects.create(
            invoice=inv_disc,
            product_name="Cloud Plan",
            quantity=1,
            unit_price=Decimal("100.00"),
            discount_amount=Decimal("20.00"),
            tax_amount=Decimal("0.00"),
            line_total=Decimal("80.00"),
        )
        InvoiceDiscount.objects.create(invoice=inv_disc, discount_id=1, amount=Decimal("20.00"))

        priced_mock = {
            "lines": [
                {
                    "product_id": line.product_id,
                    "variant_id": line.variant_id,
                    "product_name": line.product_name,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "discount_amount": Decimal("0.00"),
                    "tax_amount": Decimal("0.00"),
                    "line_total": Decimal("100.00"),
                }
            ],
            "discount_lines": [],
            "totals": {
                "subtotal": Decimal("100.00"),
                "discount_total": Decimal("0.00"),
                "tax_total": Decimal("0.00"),
                "total": Decimal("100.00"),
            },
        }

        with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", True):
            with patch.object(integrations, "USE_REAL_PRICING", True):
                with patch.object(
                    integrations,
                    "redeem_discounts",
                    return_value={"all_recorded": False, "recorded": [], "failed_ids": [1]},
                ):
                    with patch.object(integrations, "price_invoice_lines", return_value=priced_mock):
                        resp_fallback = self.client.post(f"/api/billing/invoices/{inv_disc.id}/confirm/")
                        self.assertEqual(resp_fallback.status_code, status.HTTP_200_OK)
                        self.assertTrue(resp_fallback.data["data"]["amounts_changed"])
                        self.assertEqual(resp_fallback.data["data"]["invoice"]["total"], "100.00")

        # E. Second-attempt failure -> 400 with exception message
        inv_fail2 = self._create_invoice(self.customer1, status=Invoice.Status.DRAFT)
        InvoiceLine.objects.create(
            invoice=inv_fail2,
            product_name="Service Item",
            quantity=1,
            unit_price=Decimal("100.00"),
            discount_amount=Decimal("10.00"),
            line_total=Decimal("90.00"),
        )
        InvoiceDiscount.objects.create(invoice=inv_fail2, discount_id=5, amount=Decimal("10.00"))

        priced_fail2 = {
            "lines": [
                {
                    "quantity": 1,
                    "unit_price": Decimal("100.00"),
                    "discount_amount": Decimal("5.00"),
                    "tax_amount": Decimal("0.00"),
                    "line_total": Decimal("95.00"),
                }
            ],
            "discount_lines": [{"discount_id": 6, "amount": Decimal("5.00")}],
            "totals": {
                "subtotal": Decimal("100.00"),
                "discount_total": Decimal("5.00"),
                "tax_total": Decimal("0.00"),
                "total": Decimal("95.00"),
            },
        }

        # First redeem fails (triggers repricing), second redeem on discount 6 also fails (returns all_recorded=False)
        with patch.object(integrations, "USE_REAL_DISCOUNT_USAGE", True):
            with patch.object(integrations, "USE_REAL_PRICING", True):
                with patch.object(
                    integrations,
                    "redeem_discounts",
                    return_value={"all_recorded": False, "recorded": [], "failed_ids": [6]},
                ):
                    with patch.object(integrations, "price_invoice_lines", return_value=priced_fail2):
                        resp_fail2 = self.client.post(f"/api/billing/invoices/{inv_fail2.id}/confirm/")
                        self.assertEqual(resp_fail2.status_code, status.HTTP_400_BAD_REQUEST)
                        self.assertIn("discount no longer available, please retry", resp_fail2.data["message"])

    # -------------------------------------------------------------------------
    # 6. Cancel Actions
    # -------------------------------------------------------------------------
    def test_cancel_actions(self):
        """Cancel draft and confirmed OK; cancel with amount_paid > 0 -> 409."""
        self.client.force_authenticate(user=self.staff_user)

        # Cancel draft
        inv_draft = self._create_invoice(self.customer1, status=Invoice.Status.DRAFT)
        resp_draft = self.client.post(f"/api/billing/invoices/{inv_draft.id}/cancel/")
        self.assertEqual(resp_draft.status_code, status.HTTP_200_OK)
        self.assertTrue(resp_draft.data["success"])
        self.assertEqual(resp_draft.data["data"]["status"], Invoice.Status.CANCELLED)

        # Cancel confirmed
        inv_conf = self._create_invoice(self.customer1, status=Invoice.Status.CONFIRMED)
        resp_conf = self.client.post(f"/api/billing/invoices/{inv_conf.id}/cancel/")
        self.assertEqual(resp_conf.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_conf.data["data"]["status"], Invoice.Status.CANCELLED)

        # Cancel with amount_paid > 0 -> 409 Conflict
        inv_paid = self._create_invoice(
            self.customer1,
            status=Invoice.Status.CONFIRMED,
            total=Decimal("100.00"),
            amount_paid=Decimal("25.00"),
        )
        resp_paid = self.client.post(f"/api/billing/invoices/{inv_paid.id}/cancel/")
        self.assertEqual(resp_paid.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(resp_paid.data["success"])
        self.assertIn("invoice has recorded payments", resp_paid.data["message"])

    # -------------------------------------------------------------------------
    # 7. Generate Action
    # -------------------------------------------------------------------------
    def test_generate_action(self):
        """POST generate/ works, returns JSON-safe summary, idempotent, 400 on bad date, route not captured as id."""
        self.client.force_authenticate(user=self.staff_user)

        due = [
            {
                "id": 901,
                "customer_id": self.customer1.id,
                "period_start": date(2026, 5, 1),
                "period_end": date(2026, 5, 31),
                "lines": [{"product_id": 1, "unit_price": Decimal("50.00"), "quantity": 1}],
            }
        ]
        fake = FakeSubscriptionsService(due)

        def mock_price(lines, billing_date=None):
            return {
                "lines": [
                    {
                        "product_id": 1,
                        "quantity": 1,
                        "unit_price": Decimal("50.00"),
                        "discount_amount": Decimal("0.00"),
                        "tax_amount": Decimal("0.00"),
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
                with patch.object(integrations, "price_invoice_lines", side_effect=mock_price):
                    resp = self.client.post("/api/billing/invoices/generate/", {"target_date": "2026-05-01"})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["success"])
        self.assertEqual(resp.data["data"]["created"], 1)

        # JSON round-trip verifies no raw dates
        json_str = json.dumps(resp.data)
        parsed = json.loads(json_str)
        self.assertEqual(parsed["data"]["created"], 1)

        # Re-run creates no duplicates (idempotent)
        fake2 = FakeSubscriptionsService(due)
        with patch.object(integrations, "get_due_subscriptions", side_effect=fake2.get_due_subscriptions):
            with patch.object(integrations, "advance_next_billing_date", side_effect=fake2.advance_next_billing_date):
                with patch.object(integrations, "price_invoice_lines", side_effect=mock_price):
                    resp2 = self.client.post("/api/billing/invoices/generate/", {"target_date": "2026-05-01"})
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertEqual(resp2.data["data"]["created"], 0)
        self.assertEqual(resp2.data["data"]["skipped_existing"], 1)

        # Bad target_date -> 400
        resp_bad = self.client.post("/api/billing/invoices/generate/", {"target_date": "not-a-date"})
        self.assertEqual(resp_bad.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(resp_bad.data["success"])

    # -------------------------------------------------------------------------
    # 8. Money Representation in Responses
    # -------------------------------------------------------------------------
    def test_money_representation_is_two_decimal_string(self):
        """All money amounts in list, detail, and confirm data are 2-decimal strings."""
        inv = self._create_invoice(self.customer1, status=Invoice.Status.DRAFT, total=Decimal("118.00"))
        InvoiceLine.objects.create(
            invoice=inv,
            product_name="Item 1",
            quantity=1,
            unit_price=Decimal("100.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("18.00"),
            line_total=Decimal("118.00"),
        )
        self.client.force_authenticate(user=self.staff_user)

        # List
        resp_list = self.client.get(f"/api/billing/invoices/?search={inv.number or inv.id}")
        item = resp_list.data["results"][0]
        self.assertEqual(item["total"], "118.00")
        self.assertIsInstance(item["total"], str)

        # Detail
        resp_detail = self.client.get(f"/api/billing/invoices/{inv.id}/")
        self.assertEqual(resp_detail.data["total"], "118.00")
        self.assertEqual(resp_detail.data["lines"][0]["unit_price"], "100.00")
        self.assertEqual(resp_detail.data["lines"][0]["tax_amount"], "18.00")
        self.assertEqual(resp_detail.data["lines"][0]["line_total"], "118.00")
        self.assertIsInstance(resp_detail.data["lines"][0]["line_total"], str)

    # -------------------------------------------------------------------------
    # 9. Success and Error Response Envelopes
    # -------------------------------------------------------------------------
    def test_response_envelopes(self):
        """Action success returns {success, message, data}; errors return {success, message, errors}."""
        self.client.force_authenticate(user=self.staff_user)

        inv = self._create_invoice(self.customer1, status=Invoice.Status.DRAFT)
        resp_succ = self.client.post(f"/api/billing/invoices/{inv.id}/cancel/")
        self.assertEqual(resp_succ.status_code, status.HTTP_200_OK)
        self.assertIn("success", resp_succ.data)
        self.assertIn("message", resp_succ.data)
        self.assertIn("data", resp_succ.data)
        self.assertTrue(resp_succ.data["success"])

        # Error
        resp_err = self.client.post(f"/api/billing/invoices/{inv.id}/confirm/")
        self.assertEqual(resp_err.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("success", resp_err.data)
        self.assertIn("message", resp_err.data)
        self.assertIn("errors", resp_err.data)
        self.assertFalse(resp_err.data["success"])

    # -------------------------------------------------------------------------
    # 10. CSRF Enforcement on Session Auth
    # -------------------------------------------------------------------------
    def test_csrf_enforcement_on_session_auth(self):
        """APIClient with enforce_csrf_checks=True rejects POST without CSRF token (403)."""
        client = APIClient(enforce_csrf_checks=True)
        # Login via session
        client.login(email="staff_api@example.com", password="testpassword123")
        inv = self._create_invoice(self.customer1, status=Invoice.Status.DRAFT)

        # POST without X-CSRFToken -> 403 Forbidden
        resp = client.post(f"/api/billing/invoices/{inv.id}/confirm/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # -------------------------------------------------------------------------
    # 11. Query Count Assertions (No N+1)
    # -------------------------------------------------------------------------
    def test_query_counts_constant(self):
        """List query count is constant for 3 and 15 invoices; detail count is constant regardless of line count."""
        self.client.force_authenticate(user=self.staff_user)

        # Create 3 invoices
        for i in range(3):
            inv = self._create_invoice(self.customer1, number=f"INV-QC-00{i}")
            InvoiceLine.objects.create(
                invoice=inv,
                product_name="Test Product",
                quantity=1,
                unit_price=Decimal("10.00"),
                line_total=Decimal("10.00"),
            )

        with self.assertNumQueries(2):
            # 1 COUNT query for paginator + 1 SELECT query with joined customer table
            resp3 = self.client.get("/api/billing/invoices/?search=INV-QC")
            self.assertEqual(resp3.status_code, status.HTTP_200_OK)
            self.assertEqual(len(resp3.data["results"]), 3)

        # Add 12 more invoices (total 15)
        for i in range(3, 15):
            inv = self._create_invoice(self.customer1, number=f"INV-QC-0{i:02d}")
            InvoiceLine.objects.create(
                invoice=inv,
                product_name="Test Product",
                quantity=1,
                unit_price=Decimal("10.00"),
                line_total=Decimal("10.00"),
            )

        with self.assertNumQueries(2):
            resp15 = self.client.get("/api/billing/invoices/?search=INV-QC")
            self.assertEqual(resp15.status_code, status.HTTP_200_OK)
            self.assertEqual(len(resp15.data["results"]), 15)

        # Detail query count: constant regardless of line count
        inv_single_line = self._create_invoice(self.customer1, number="INV-DET-1")
        InvoiceLine.objects.create(
            invoice=inv_single_line,
            product_name="Line 1",
            quantity=1,
            unit_price=Decimal("10.00"),
            line_total=Decimal("10.00"),
        )
        InvoiceDiscount.objects.create(invoice=inv_single_line, discount_id=1, amount=Decimal("1.00"))

        inv_multi_line = self._create_invoice(self.customer1, number="INV-DET-10")
        for k in range(10):
            InvoiceLine.objects.create(
                invoice=inv_multi_line,
                product_name=f"Line {k}",
                quantity=1,
                unit_price=Decimal("10.00"),
                line_total=Decimal("10.00"),
            )
        for d in range(5):
            InvoiceDiscount.objects.create(invoice=inv_multi_line, discount_id=d + 1, amount=Decimal("1.00"))

        # Measure query count for single-line invoice: 1 invoice + customer, 1 lines, 1 discounts = 3 queries
        with self.assertNumQueries(3):
            resp_det1 = self.client.get(f"/api/billing/invoices/{inv_single_line.id}/")
            self.assertEqual(resp_det1.status_code, status.HTTP_200_OK)

        # Multi-line invoice must also take exactly 3 queries
        with self.assertNumQueries(3):
            resp_det10 = self.client.get(f"/api/billing/invoices/{inv_multi_line.id}/")
            self.assertEqual(resp_det10.status_code, status.HTTP_200_OK)

    # -------------------------------------------------------------------------
    # 12. Disallowed HTTP Methods (405)
    # -------------------------------------------------------------------------
    def test_disallowed_http_methods_return_405(self):
        """POST/PUT/PATCH/DELETE on collection and detail return 405 Method Not Allowed."""
        self.client.force_authenticate(user=self.staff_user)
        inv = self._create_invoice(self.customer1)

        # Collection POST
        resp_post = self.client.post("/api/billing/invoices/", {"total": "100.00"})
        self.assertEqual(resp_post.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Detail PUT
        resp_put = self.client.put(f"/api/billing/invoices/{inv.id}/", {"total": "100.00"})
        self.assertEqual(resp_put.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Detail PATCH
        resp_patch = self.client.patch(f"/api/billing/invoices/{inv.id}/", {"total": "100.00"})
        self.assertEqual(resp_patch.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Detail DELETE
        resp_delete = self.client.delete(f"/api/billing/invoices/{inv.id}/")
        self.assertEqual(resp_delete.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
