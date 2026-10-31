"""
billing/management/commands/time_billing.py

Benchmark billing and payment API endpoints and selectors.
Times requests 3 times each, capturing min/median/max milliseconds and query counts.
Runs benchmarks as ADMIN and as a CUSTOMER with many invoices.
"""
import statistics
import time
from datetime import date
from typing import Callable, List, Tuple

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

User = get_user_model()


class Command(BaseCommand):
    help = "Benchmark billing and payment API endpoints and selectors (min/med/max ms, queries)."

    def handle(self, *args, **options):
        admin_user = User.objects.filter(role="ADMIN").order_by("id").first()
        if not admin_user:
            raise CommandError("No ADMIN user found.")

        # Find customer with the most invoices
        customer_user = (
            User.objects.filter(role="CUSTOMER")
            .annotate(inv_count=Count("invoices"))
            .order_by("-inv_count")
            .first()
        )
        if not customer_user:
            customer_user = User.objects.filter(role="CUSTOMER").order_by("id").first()

        from apps.billing.models import Invoice
        first_invoice = Invoice.objects.first()
        sample_inv_number = first_invoice.number if first_invoice else "INV-2026-000001"
        sample_cust_id = customer_user.id if customer_user else 1

        cust_invoice = None
        if customer_user:
            cust_invoice = Invoice.objects.filter(customer=customer_user).first()
        sample_cust_inv_number = cust_invoice.number if cust_invoice else sample_inv_number

        from apps.billing import selectors as billing_selectors
        from apps.payments import selectors as payments_selectors

        self.stdout.write("=" * 80)
        self.stdout.write("BILLING & PAYMENTS PERFORMANCE BENCHMARK")
        self.stdout.write(f"Admin User:    {admin_user.email} (id={admin_user.id})")
        if customer_user:
            inv_c = getattr(customer_user, "inv_count", 0)
            self.stdout.write(f"Customer User: {customer_user.email} (id={customer_user.id}, invoices={inv_c})")
        self.stdout.write("=" * 80)

        # -------------------------------------------------------------
        # Benchmark definitions for ADMIN
        # -------------------------------------------------------------
        client_admin = APIClient(SERVER_NAME="localhost", HTTP_HOST="localhost")
        client_admin.force_authenticate(user=admin_user)

        admin_benchmarks = [
            ("GET /api/billing/invoices/", lambda: client_admin.get("/api/billing/invoices/", HTTP_HOST="localhost")),
            ("GET /api/billing/invoices/?status=confirmed", lambda: client_admin.get("/api/billing/invoices/?status=confirmed", HTTP_HOST="localhost")),
            ("GET /api/billing/invoices/?overdue=true", lambda: client_admin.get("/api/billing/invoices/?overdue=true", HTTP_HOST="localhost")),
            ("GET /api/billing/invoices/?search=INV-2026", lambda: client_admin.get("/api/billing/invoices/?search=INV-2026", HTTP_HOST="localhost")),
            ("GET /api/billing/invoices/?ordering=-total", lambda: client_admin.get("/api/billing/invoices/?ordering=-total", HTTP_HOST="localhost")),
            ("GET /api/billing/invoices/?page=50", lambda: client_admin.get("/api/billing/invoices/?page=50", HTTP_HOST="localhost")),
            (f"GET /api/billing/invoices/?customer={sample_cust_id}", lambda: client_admin.get(f"/api/billing/invoices/?customer={sample_cust_id}", HTTP_HOST="localhost")),
            ("GET /api/payments/", lambda: client_admin.get("/api/payments/", HTTP_HOST="localhost")),
            ("GET /api/payments/?method=card", lambda: client_admin.get("/api/payments/?method=card", HTTP_HOST="localhost")),
            ("GET /api/payments/?date_from=2026-01-01&date_to=2026-12-31", lambda: client_admin.get("/api/payments/?date_from=2026-01-01&date_to=2026-12-31", HTTP_HOST="localhost")),
            (f"GET /api/payments/?invoice={sample_inv_number}", lambda: client_admin.get(f"/api/payments/?invoice={sample_inv_number}", HTTP_HOST="localhost")),
            ("Selector: outstanding_total()", lambda: billing_selectors.outstanding_total()),
            ("Selector: overdue_total()", lambda: billing_selectors.overdue_total()),
            ("Selector: invoice_counts_by_status()", lambda: billing_selectors.invoice_counts_by_status()),
            ("Selector: revenue_between(range)", lambda: payments_selectors.revenue_between(date(2000, 1, 1), date(2099, 12, 31))),
        ]

        # -------------------------------------------------------------
        # Benchmark definitions for CUSTOMER
        # -------------------------------------------------------------
        customer_benchmarks = []
        if customer_user:
            client_cust = APIClient(SERVER_NAME="localhost", HTTP_HOST="localhost")
            client_cust.force_authenticate(user=customer_user)
            cust_id = customer_user.id
            customer_benchmarks = [
                ("GET /api/billing/invoices/", lambda: client_cust.get("/api/billing/invoices/", HTTP_HOST="localhost")),
                ("GET /api/billing/invoices/?status=confirmed", lambda: client_cust.get("/api/billing/invoices/?status=confirmed", HTTP_HOST="localhost")),
                ("GET /api/billing/invoices/?overdue=true", lambda: client_cust.get("/api/billing/invoices/?overdue=true", HTTP_HOST="localhost")),
                ("GET /api/billing/invoices/?search=INV-2026", lambda: client_cust.get("/api/billing/invoices/?search=INV-2026", HTTP_HOST="localhost")),
                ("GET /api/billing/invoices/?ordering=-total", lambda: client_cust.get("/api/billing/invoices/?ordering=-total", HTTP_HOST="localhost")),
                ("GET /api/billing/invoices/?page=50", lambda: client_cust.get("/api/billing/invoices/?page=50", HTTP_HOST="localhost")),
                ("GET /api/payments/", lambda: client_cust.get("/api/payments/", HTTP_HOST="localhost")),
                ("GET /api/payments/?method=card", lambda: client_cust.get("/api/payments/?method=card", HTTP_HOST="localhost")),
                ("GET /api/payments/?date_from=2026-01-01&date_to=2026-12-31", lambda: client_cust.get("/api/payments/?date_from=2026-01-01&date_to=2026-12-31", HTTP_HOST="localhost")),
                (f"GET /api/payments/?invoice={sample_cust_inv_number}", lambda: client_cust.get(f"/api/payments/?invoice={sample_cust_inv_number}", HTTP_HOST="localhost")),
                ("Selector: outstanding_total(cust)", lambda: billing_selectors.outstanding_total({"customer_id": cust_id})),
                ("Selector: overdue_total(cust)", lambda: billing_selectors.overdue_total(filters={"customer_id": cust_id})),
                ("Selector: invoice_counts_by_status(cust)", lambda: billing_selectors.invoice_counts_by_status({"customer_id": cust_id})),
                ("Selector: revenue_between(cust)", lambda: payments_selectors.revenue_between(date(2000, 1, 1), date(2099, 12, 31), {"customer_id": cust_id})),
            ]

        self.stdout.write("\n### Running Benchmarks as ADMIN (3 runs each)...\n")
        admin_results = self._run_suite(admin_benchmarks)

        cust_results = []
        if customer_benchmarks:
            self.stdout.write("\n### Running Benchmarks as CUSTOMER (3 runs each)...\n")
            cust_results = self._run_suite(customer_benchmarks)

        self._print_table("ADMIN", admin_results)
        if cust_results:
            self._print_table("CUSTOMER", cust_results)

        # Check for queries > 500ms
        all_results = admin_results + cust_results
        slow = [r for r in all_results if r["max_ms"] > 500]
        if slow:
            self.stdout.write(self.style.WARNING(f"\n{len(slow)} operation(s) took > 500ms:"))
            for s in slow:
                self.stdout.write(f"  - {s['name']}: {s['max_ms']:.1f}ms")
        else:
            self.stdout.write(self.style.SUCCESS("\nAll operations completed under 500ms! Target achieved."))

    def _run_suite(self, benchmarks: List[Tuple[str, Callable]]) -> List[dict]:
        results = []
        for name, fn in benchmarks:
            times = []
            query_counts = []
            status_code = None

            for _ in range(3):
                with CaptureQueriesContext(connection) as ctx:
                    t0 = time.perf_counter()
                    res = fn()
                    t1 = time.perf_counter()

                elapsed_ms = (t1 - t0) * 1000.0
                times.append(elapsed_ms)
                query_counts.append(len(ctx.captured_queries))
                if hasattr(res, "status_code"):
                    status_code = res.status_code

            res_dict = {
                "name": name,
                "min_ms": min(times),
                "median_ms": statistics.median(times),
                "max_ms": max(times),
                "queries": query_counts[-1],
                "status": status_code,
            }
            results.append(res_dict)
        return results

    def _print_table(self, role: str, results: List[dict]):
        self.stdout.write(f"\n| Operation ({role}) | Min (ms) | Median (ms) | Max (ms) | Queries | Status |")
        self.stdout.write("| :--- | :---: | :---: | :---: | :---: | :---: |")
        for r in results:
            stat_str = str(r["status"]) if r["status"] is not None else "OK"
            self.stdout.write(
                f"| `{r['name']}` | {r['min_ms']:.1f} | {r['median_ms']:.1f} | {r['max_ms']:.1f} | {r['queries']} | {stat_str} |"
            )
