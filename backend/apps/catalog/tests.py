from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.catalog.models import Discount, DiscountUsage, Plan, Product, ProductVariant, Tax
from apps.catalog.services import (
    Line,
    calculate_tax,
    get_line_price,
    price_invoice,
    record_discount_usage,
)

User = get_user_model()


class CatalogAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            "admin@t.com", password="x", role="ADMIN"
        )
        self.staff = User.objects.create_user(
            "staff@t.com", password="x", role="STAFF"
        )
        self.customer = User.objects.create_user(
            "customer@t.com", password="x", role="CUSTOMER"
        )

        self.tax18 = Tax.objects.create(
            name="GST 18%", kind=Tax.Kind.PERCENT, rate=Decimal("18.00")
        )
        self.product = Product.objects.create(
            name="CRM",
            type="software",
            sales_price=Decimal("2000.00"),
            cost_price=Decimal("800.00"),
            notes="Confidential internal notes",
            tax=self.tax18,
            is_active=True,
        )

    def test_anonymous_is_blocked(self):
        """Anonymous requests must receive 401 or 403."""
        for endpoint in ["/api/catalog/products/", "/api/catalog/taxes/", "/api/catalog/discounts/"]:
            resp = self.client.get(endpoint)
            self.assertIn(resp.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_admin_creates_product_and_variant(self):
        """Admin can create a product and a Brand=Odoo +560 variant."""
        self.client.force_authenticate(user=self.admin)
        prod_resp = self.client.post(
            "/api/catalog/products/",
            {
                "name": "ERP Suite",
                "type": "software",
                "sales_price": "5000.00",
                "cost_price": "2000.00",
                "notes": "Admin notes",
            },
            format="json",
        )
        self.assertEqual(prod_resp.status_code, status.HTTP_201_CREATED)
        product_id = prod_resp.data["id"]

        var_resp = self.client.post(
            f"/api/catalog/products/{product_id}/variants/",
            {
                "attribute": "Brand",
                "value": "Odoo",
                "extra_price": "560.00",
            },
            format="json",
        )
        self.assertEqual(var_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(var_resp.data["attribute"], "Brand")
        self.assertEqual(var_resp.data["value"], "Odoo")
        self.assertEqual(Decimal(str(var_resp.data["extra_price"])), Decimal("560.00"))

    def test_duplicate_variant_returns_400(self):
        """Creating duplicate variant on (product, attribute, value) returns 400."""
        self.client.force_authenticate(user=self.admin)
        first_resp = self.client.post(
            f"/api/catalog/products/{self.product.id}/variants/",
            {"attribute": "Brand", "value": "Odoo", "extra_price": "560.00"},
            format="json",
        )
        self.assertEqual(first_resp.status_code, status.HTTP_201_CREATED)

        dup_resp = self.client.post(
            f"/api/catalog/products/{self.product.id}/variants/",
            {"attribute": "Brand", "value": "Odoo", "extra_price": "560.00"},
            format="json",
        )
        self.assertEqual(dup_resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_staff_and_customer_cannot_write_products_or_plans(self):
        """Staff and customer users cannot create products or plans (403)."""
        payload = {
            "name": "Forbidden Prod",
            "type": "software",
            "sales_price": "100.00",
            "cost_price": "50.00",
        }
        for user in [self.staff, self.customer]:
            self.client.force_authenticate(user=user)
            resp = self.client.post("/api/catalog/products/", payload, format="json")
            self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

            plan_resp = self.client.post(
                "/api/catalog/plans/",
                {
                    "name": "Forbidden Plan",
                    "price": "100.00",
                    "billing_period": "monthly",
                    "available_from": str(date.today()),
                },
                format="json",
            )
            self.assertEqual(plan_resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_customer_does_not_see_cost_price_or_notes(self):
        """Customer role must not receive cost_price or notes in product output."""
        self.client.force_authenticate(user=self.customer)
        resp = self.client.get(f"/api/catalog/products/{self.product.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("cost_price", resp.data)
        self.assertNotIn("notes", resp.data)

        # Admin must see them
        self.client.force_authenticate(user=self.admin)
        admin_resp = self.client.get(f"/api/catalog/products/{self.product.id}/")
        self.assertEqual(admin_resp.status_code, status.HTTP_200_OK)
        self.assertIn("cost_price", admin_resp.data)
        self.assertIn("notes", admin_resp.data)

    def test_delete_deactivates_and_returns_200(self):
        """DELETE sets is_active=False and returns HTTP 200 with specific JSON message."""
        self.client.force_authenticate(user=self.admin)
        resp = self.client.delete(f"/api/catalog/products/{self.product.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, {"success": True, "message": "Deactivated"})

        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)

    def test_delete_variant_deactivates_and_returns_200(self):
        """DELETE variant sets is_active=False and returns HTTP 200 with specific JSON."""
        variant = ProductVariant.objects.create(
            product=self.product, attribute="Brand", value="Odoo", extra_price=Decimal("560.00")
        )
        self.client.force_authenticate(user=self.admin)
        resp = self.client.delete(f"/api/catalog/products/{self.product.id}/variants/{variant.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, {"success": True, "message": "Deactivated"})

        variant.refresh_from_db()
        self.assertFalse(variant.is_active)

    def test_plan_with_invalid_dates_returns_400(self):
        """Plan with available_to before available_from returns 400."""
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            "/api/catalog/plans/",
            {
                "name": "Invalid Plan",
                "price": "100.00",
                "billing_period": "monthly",
                "available_from": "2026-11-10",
                "available_to": "2026-11-01",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_plan_four_flags_are_saved(self):
        """Plan auto_close, closable, pausable, and renewable flags are saved."""
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            "/api/catalog/plans/",
            {
                "name": "Custom Flags Plan",
                "price": "99.00",
                "billing_period": "yearly",
                "available_from": str(date.today()),
                "auto_close": True,
                "closable": False,
                "pausable": True,
                "renewable": False,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp.data["auto_close"])
        self.assertFalse(resp.data["closable"])
        self.assertTrue(resp.data["pausable"])
        self.assertFalse(resp.data["renewable"])

    def test_plan_available_filter(self):
        """?available=true filter returns only currently available active plans."""
        today = date.today()
        yesterday = today - timedelta(days=1)
        future = today + timedelta(days=30)

        # Plan 1: available
        Plan.objects.create(
            name="Available Plan",
            price=Decimal("10.00"),
            billing_period="monthly",
            available_from=yesterday,
            available_to=future,
            is_active=True,
        )
        # Plan 2: inactive
        Plan.objects.create(
            name="Inactive Plan",
            price=Decimal("10.00"),
            billing_period="monthly",
            available_from=yesterday,
            available_to=future,
            is_active=False,
        )
        # Plan 3: future available_from
        Plan.objects.create(
            name="Future Plan",
            price=Decimal("10.00"),
            billing_period="monthly",
            available_from=future,
            available_to=future + timedelta(days=10),
            is_active=True,
        )

        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/catalog/plans/?available=true")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [p["name"] for p in resp.data["results"]]
        self.assertIn("Available Plan", names)
        self.assertNotIn("Inactive Plan", names)
        self.assertNotIn("Future Plan", names)

    def test_discount_validation(self):
        """150% percent, end_date equal to start_date, and product scope without product return 400."""
        self.client.force_authenticate(user=self.admin)
        today = date.today()

        # 1. Percent > 100
        resp1 = self.client.post(
            "/api/catalog/discounts/",
            {
                "name": "Excessive Discount",
                "kind": "percent",
                "value": "150.00",
                "scope": "subscription",
                "usage_limit": 10,
                "start_date": str(today),
                "end_date": str(today + timedelta(days=10)),
            },
            format="json",
        )
        self.assertEqual(resp1.status_code, status.HTTP_400_BAD_REQUEST)

        # 2. end_date equal to start_date
        resp2 = self.client.post(
            "/api/catalog/discounts/",
            {
                "name": "Zero Duration Discount",
                "kind": "percent",
                "value": "10.00",
                "scope": "subscription",
                "usage_limit": 10,
                "start_date": str(today),
                "end_date": str(today),
            },
            format="json",
        )
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)

        # 3. product scope without product
        resp3 = self.client.post(
            "/api/catalog/discounts/",
            {
                "name": "Missing Product Discount",
                "kind": "fixed",
                "value": "100.00",
                "scope": "product",
                "usage_limit": 10,
                "start_date": str(today),
                "end_date": str(today + timedelta(days=10)),
            },
            format="json",
        )
        self.assertEqual(resp3.status_code, status.HTTP_400_BAD_REQUEST)

    def test_customer_gets_403_on_discounts_and_taxes(self):
        """Customer gets 403 on discounts and taxes endpoints."""
        self.client.force_authenticate(user=self.customer)
        for ep in ["/api/catalog/discounts/", "/api/catalog/taxes/"]:
            resp = self.client.get(ep)
            self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_read_but_not_write_discounts(self):
        """Staff has read-only access to discounts (cannot POST/PUT/PATCH/DELETE)."""
        self.client.force_authenticate(user=self.staff)
        get_resp = self.client.get("/api/catalog/discounts/")
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)

        post_resp = self.client.post(
            "/api/catalog/discounts/",
            {
                "name": "Staff Discount",
                "kind": "percent",
                "value": "10.00",
                "scope": "subscription",
                "usage_limit": 10,
                "start_date": str(date.today()),
                "end_date": str(date.today() + timedelta(days=5)),
            },
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_used_count_is_not_writable(self):
        """used_count is read-only and cannot be set on create/update."""
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            "/api/catalog/discounts/",
            {
                "name": "Admin Discount",
                "kind": "percent",
                "value": "10.00",
                "scope": "subscription",
                "usage_limit": 100,
                "used_count": 55,
                "start_date": str(date.today()),
                "end_date": str(date.today() + timedelta(days=10)),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["used_count"], 0)

    def test_discount_usage_action_works(self):
        """GET discounts/{id}/usage/ returns paginated usage records."""
        discount = Discount.objects.create(
            name="Promo 10",
            kind="percent",
            value=Decimal("10.00"),
            scope="subscription",
            usage_limit=10,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=5),
        )
        DiscountUsage.objects.create(
            discount=discount, invoice_id=501, subscription_id=601
        )

        self.client.force_authenticate(user=self.staff)
        resp = self.client.get(f"/api/catalog/discounts/{discount.id}/usage/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["invoice_id"], 501)
        self.assertEqual(resp.data["results"][0]["subscription_id"], 601)

    def test_pagination_and_search_work(self):
        """Search and pagination work as expected on catalog endpoints."""
        self.client.force_authenticate(user=self.admin)
        Product.objects.create(
            name="Accounting Module",
            type="software",
            sales_price=Decimal("3000.00"),
            cost_price=Decimal("1000.00"),
        )
        Product.objects.create(
            name="Helpdesk Pro",
            type="service",
            sales_price=Decimal("1500.00"),
            cost_price=Decimal("500.00"),
        )

        # Search
        search_resp = self.client.get("/api/catalog/products/?search=Accounting")
        self.assertEqual(search_resp.status_code, status.HTTP_200_OK)
        names = [p["name"] for p in search_resp.data["results"]]
        self.assertEqual(names, ["Accounting Module"])

        # Pagination
        page_resp = self.client.get("/api/catalog/products/?page=1&page_size=2")
        self.assertEqual(page_resp.status_code, status.HTTP_200_OK)
        self.assertIn("count", page_resp.data)
        self.assertIn("results", page_resp.data)
        self.assertEqual(len(page_resp.data["results"]), 2)


class CatalogServiceTests(TestCase):
    def setUp(self):
        self.today = date.today()
        self.yesterday = self.today - timedelta(days=1)
        self.future = self.today + timedelta(days=30)

        self.tax18 = Tax.objects.create(
            name="GST 18%", kind=Tax.Kind.PERCENT, rate=Decimal("18.00")
        )
        self.product = Product.objects.create(
            name="CRM",
            type="software",
            sales_price=Decimal("1000.00"),
            cost_price=Decimal("400.00"),
            tax=self.tax18,
            is_active=True,
        )

    def test_percent_discount(self):
        """Percent discount on subscription calculates correctly."""
        Discount.objects.create(
            name="10% Sub",
            kind="percent",
            value=Decimal("10.00"),
            scope="subscription",
            usage_limit=10,
            start_date=self.yesterday,
            end_date=self.future,
        )
        inv = price_invoice([Line(self.product.id, 1, Decimal("1000.00"))], self.today)
        self.assertEqual(inv.subtotal, Decimal("1000.00"))
        self.assertEqual(inv.discount_total, Decimal("1000.00") * Decimal("0.10"))
        self.assertEqual(inv.total, Decimal("900.00"))

    def test_fixed_discount_capped_at_subtotal(self):
        """Fixed discount larger than subtotal is capped and does not go below zero."""
        Discount.objects.create(
            name="Huge Fixed",
            kind="fixed",
            value=Decimal("5000.00"),
            scope="subscription",
            usage_limit=10,
            start_date=self.yesterday,
            end_date=self.future,
        )
        inv = price_invoice([Line(self.product.id, 1, Decimal("1000.00"))], self.today)
        self.assertEqual(inv.subtotal, Decimal("1000.00"))
        self.assertEqual(inv.discount_total, Decimal("1000.00"))
        self.assertEqual(inv.total, Decimal("0.00"))

    def test_below_min_purchase_gives_no_discount(self):
        """Purchase below min_purchase does not receive discount."""
        Discount.objects.create(
            name="Min 2000 Required",
            kind="percent",
            value=Decimal("15.00"),
            min_purchase=Decimal("2000.00"),
            scope="subscription",
            usage_limit=10,
            start_date=self.yesterday,
            end_date=self.future,
        )
        inv = price_invoice([Line(self.product.id, 1, Decimal("1000.00"))], self.today)
        self.assertEqual(inv.discount_total, Decimal("0.00"))

    def test_below_min_quantity_gives_no_discount(self):
        """Quantity below min_quantity does not receive discount."""
        Discount.objects.create(
            name="Min Qty 5",
            kind="percent",
            value=Decimal("20.00"),
            min_quantity=5,
            scope="subscription",
            usage_limit=10,
            start_date=self.yesterday,
            end_date=self.future,
        )
        inv = price_invoice([Line(self.product.id, 2, Decimal("1000.00"))], self.today)
        self.assertEqual(inv.discount_total, Decimal("0.00"))

    def test_expired_discount(self):
        """Discount whose end_date has passed is not applied."""
        Discount.objects.create(
            name="Expired Promo",
            kind="percent",
            value=Decimal("25.00"),
            scope="subscription",
            usage_limit=10,
            start_date=self.today - timedelta(days=10),
            end_date=self.today - timedelta(days=1),
        )
        inv = price_invoice([Line(self.product.id, 1, Decimal("1000.00"))], self.today)
        self.assertEqual(inv.discount_total, Decimal("0.00"))

    def test_usage_limit_reached(self):
        """Discount with used_count >= usage_limit is not applied."""
        Discount.objects.create(
            name="Maxed Out",
            kind="percent",
            value=Decimal("10.00"),
            scope="subscription",
            usage_limit=2,
            used_count=2,
            start_date=self.yesterday,
            end_date=self.future,
        )
        inv = price_invoice([Line(self.product.id, 1, Decimal("1000.00"))], self.today)
        self.assertEqual(inv.discount_total, Decimal("0.00"))

    def test_product_scope_hits_only_matching_line(self):
        """Product-scoped discount applies only to the line with matching product_id."""
        prod2 = Product.objects.create(
            name="Other Product",
            type="software",
            sales_price=Decimal("1000.00"),
            cost_price=Decimal("300.00"),
        )
        Discount.objects.create(
            name="CRM Only 20%",
            kind="percent",
            value=Decimal("20.00"),
            scope="product",
            product=self.product,
            usage_limit=10,
            start_date=self.yesterday,
            end_date=self.future,
        )
        lines = [
            Line(self.product.id, 1, Decimal("1000.00")),
            Line(prod2.id, 1, Decimal("1000.00")),
        ]
        inv = price_invoice(lines, self.today)
        self.assertEqual(inv.subtotal, Decimal("2000.00"))
        self.assertEqual(inv.discount_total, Decimal("200.00"))
        # First line discounted by 200, second line has 0 discount
        self.assertEqual(inv.lines[0].line_discount, Decimal("200.00"))
        self.assertEqual(inv.lines[0].net, Decimal("800.00"))
        self.assertEqual(inv.lines[1].line_discount, Decimal("0.00"))
        self.assertEqual(inv.lines[1].net, Decimal("1000.00"))

    def test_best_single_discount_wins(self):
        """When multiple eligible discounts exist, the single best discount applies."""
        Discount.objects.create(
            name="Small Sub 10%",
            kind="percent",
            value=Decimal("10.00"),
            scope="subscription",
            usage_limit=10,
            start_date=self.yesterday,
            end_date=self.future,
        )
        Discount.objects.create(
            name="Better Sub 25%",
            kind="percent",
            value=Decimal("25.00"),
            scope="subscription",
            usage_limit=10,
            start_date=self.yesterday,
            end_date=self.future,
        )
        inv = price_invoice([Line(self.product.id, 1, Decimal("1000.00"))], self.today)
        self.assertEqual(inv.discount_total, Decimal("250.00"))
        self.assertEqual(inv.total, Decimal("750.00"))

    def test_tax_on_discounted_line(self):
        """Tax on discounted line: 1000 gross, 10% off (net 900), 18% tax = 162.00, total = 1062.00."""
        Discount.objects.create(
            name="Ten Percent",
            kind="percent",
            value=Decimal("10.00"),
            scope="subscription",
            usage_limit=10,
            start_date=self.yesterday,
            end_date=self.future,
        )
        inv = price_invoice(
            [Line(self.product.id, 1, Decimal("1000.00"), tax_id=self.tax18.id)],
            self.today,
        )
        self.assertEqual(inv.subtotal, Decimal("1000.00"))
        self.assertEqual(inv.discount_total, Decimal("100.00"))
        self.assertEqual(inv.tax_total, Decimal("162.00"))
        self.assertEqual(inv.total, Decimal("1062.00"))

    def test_variant_extra_price_via_get_line_price(self):
        """variant +560 via get_line_price yields 1560.00."""
        variant = ProductVariant.objects.create(
            product=self.product,
            attribute="Brand",
            value="Odoo",
            extra_price=Decimal("560.00"),
        )
        price = get_line_price(self.product.id, variant.id)
        self.assertEqual(price, Decimal("1560.00"))

    def test_three_lines_of_33_33_at_18_percent_tax_total_18(self):
        """3 lines of 33.33 at 18% tax yield a total of 18.00 tax."""
        lines = [
            Line(self.product.id, 1, Decimal("33.33"), tax_id=self.tax18.id),
            Line(self.product.id, 1, Decimal("33.33"), tax_id=self.tax18.id),
            Line(self.product.id, 1, Decimal("33.33"), tax_id=self.tax18.id),
        ]
        updated_lines, total_tax = calculate_tax(lines)
        # 33.33 * 0.18 = 5.9994 -> 6.00 per line * 3 = 18.00
        self.assertEqual(total_tax, Decimal("18.00"))
        for line in updated_lines:
            self.assertEqual(line.tax_amount, Decimal("6.00"))

    def test_record_discount_usage(self):
        """record_discount_usage: first call True, duplicate True without increment, over-limit False."""
        discount = Discount.objects.create(
            name="OneTime",
            kind="fixed",
            value=Decimal("50.00"),
            scope="subscription",
            usage_limit=1,
            used_count=0,
            start_date=self.yesterday,
            end_date=self.future,
        )
        # 1. First call -> True, used_count becomes 1
        res1 = record_discount_usage(discount.id, invoice_id=1001, subscription_id=1)
        self.assertTrue(res1)
        discount.refresh_from_db()
        self.assertEqual(discount.used_count, 1)

        # 2. Repeat for same invoice -> True, used_count stays 1
        res2 = record_discount_usage(discount.id, invoice_id=1001, subscription_id=1)
        self.assertTrue(res2)
        discount.refresh_from_db()
        self.assertEqual(discount.used_count, 1)

        # 3. Over-limit call with different invoice -> False, used_count stays 1
        res3 = record_discount_usage(discount.id, invoice_id=1002, subscription_id=1)
        self.assertFalse(res3)
        discount.refresh_from_db()
        self.assertEqual(discount.used_count, 1)
        self.assertFalse(
            DiscountUsage.objects.filter(discount=discount, invoice_id=1002).exists()
        )
