"""
billing/management/commands/seed_billing.py

Seed billing data: generate invoices, confirm a fraction, pay a fraction.
Options control ratios and random seed for full determinism.

NOTE on --reset: safe tracking of "created by this command" would require
an extra model field or a separate tag table, which is a migration and
a model change. To stay within constraints (no model edits), --reset is
NOT implemented. Rerunning is safe because:
  - generate_invoices is idempotent (skips existing periods).
  - seed_billing only pays confirmed invoices with outstanding > 0.
"""
import math
import random
import time
from datetime import date
from decimal import Decimal
from typing import List

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import F
from django.utils import timezone

User = get_user_model()


class Command(BaseCommand):
    help = "Seed billing data: generate, confirm, and pay invoices deterministically."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            default=None,
            metavar="YYYY-MM-DD",
            help="Target billing date (default: today).",
        )
        parser.add_argument(
            "--confirm-ratio",
            type=float,
            default=0.8,
            metavar="FLOAT",
            help="Fraction of draft invoices to confirm (0-1, default 0.8).",
        )
        parser.add_argument(
            "--pay-ratio",
            type=float,
            default=0.6,
            metavar="FLOAT",
            help="Fraction of confirmed invoices to pay (0-1, default 0.6).",
        )
        parser.add_argument(
            "--partial-ratio",
            type=float,
            default=0.3,
            metavar="FLOAT",
            help="Share of payments that are partial (0-1, default 0.3).",
        )
        parser.add_argument(
            "--random-seed",
            type=int,
            default=42,
            metavar="INT",
            help="Random seed for deterministic behaviour (default 42).",
        )
        parser.add_argument(
            "--max-periods",
            type=int,
            default=3,
            metavar="INT",
            help="Max periods per subscription to generate (default 3).",
        )

    def handle(self, *args, **options):
        target_date: date
        if options["date"]:
            try:
                target_date = date.fromisoformat(options["date"])
            except ValueError:
                raise CommandError(f"Invalid date format: '{options['date']}'. Use YYYY-MM-DD.")
        else:
            target_date = timezone.localdate()

        confirm_ratio: float = options["confirm_ratio"]
        pay_ratio: float = options["pay_ratio"]
        partial_ratio: float = options["partial_ratio"]
        random_seed: int = options["random_seed"]
        max_periods: int = options["max_periods"]

        rng = random.Random(random_seed)

        # ------------------------------------------------------------------ #
        # Find the recorder (first ADMIN user)
        # ------------------------------------------------------------------ #
        admin_user = User.objects.filter(role="ADMIN").order_by("id").first()
        if admin_user is None:
            raise CommandError(
                "No ADMIN user found. Run seed_demo_data first (or create an admin)."
            )
        self.stdout.write(f"Recorder: {admin_user.email} (id={admin_user.id})")

        # ------------------------------------------------------------------ #
        # Step 1: Generate invoices
        # ------------------------------------------------------------------ #
        from apps.billing.services import generate_invoices, summary_as_dict

        self.stdout.write("\n--- Step 1: Generating invoices ---")
        t0 = time.time()
        summary = generate_invoices(
            target_date=target_date,
            max_periods_per_subscription=max_periods,
        )
        elapsed = time.time() - t0
        d = summary_as_dict(summary)
        self.stdout.write(f"  created:          {d['created']}")
        self.stdout.write(f"  skipped_existing: {d['skipped_existing']}")
        self.stdout.write(f"  advanced:         {d['advanced']}")
        self.stdout.write(f"  capped:           {d['capped']}")
        self.stdout.write(f"  errors:           {len(d['errors'])}")
        for e in d["errors"]:
            self.stdout.write(f"    [ERROR] sub={e['subscription_id']} {e['message']}")
        self.stdout.write(f"  elapsed:          {elapsed:.2f}s")

        # ------------------------------------------------------------------ #
        # Step 2: Confirm a deterministic fraction of draft invoices
        # ------------------------------------------------------------------ #
        from apps.billing.models import Invoice
        from apps.billing.services import confirm_invoice

        self.stdout.write("\n--- Step 2: Confirming invoices ---")
        draft_ids: List[int] = list(
            Invoice.objects.filter(status=Invoice.Status.DRAFT)
            .order_by("id")
            .values_list("id", flat=True)
        )
        rng.shuffle(draft_ids)
        n_confirm = max(0, min(len(draft_ids), math.ceil(len(draft_ids) * confirm_ratio)))
        to_confirm = draft_ids[:n_confirm]

        confirmed_ok = 0
        amounts_changed_count = 0
        confirm_failures = 0
        for inv_id in to_confirm:
            try:
                result = confirm_invoice(inv_id)
                confirmed_ok += 1
                if result.amounts_changed:
                    amounts_changed_count += 1
            except Exception as exc:
                confirm_failures += 1
                self.stdout.write(
                    self.style.WARNING(f"  [WARN] confirm invoice {inv_id} failed: {exc}")
                )

        self.stdout.write(f"  draft available:  {len(draft_ids)}")
        self.stdout.write(f"  to confirm:       {n_confirm}")
        self.stdout.write(f"  confirmed OK:     {confirmed_ok}")
        self.stdout.write(f"  amounts_changed:  {amounts_changed_count}")
        self.stdout.write(f"  failures:         {confirm_failures}")

        # ------------------------------------------------------------------ #
        # Step 3: Pay a fraction of confirmed invoices
        # ------------------------------------------------------------------ #
        from apps.payments.services import record_payment

        self.stdout.write("\n--- Step 3: Recording payments ---")

        # Only pay confirmed invoices with outstanding > 0
        confirmed_outstanding = list(
            Invoice.objects.filter(
                status=Invoice.Status.CONFIRMED,
            )
            .filter(total__gt=F("amount_paid"))
            .order_by("id")
            .select_related("customer")
        )

        n_pay = max(0, min(len(confirmed_outstanding), math.ceil(len(confirmed_outstanding) * pay_ratio)))

        # Group by customer
        by_customer_all: dict = {}
        for inv in confirmed_outstanding:
            by_customer_all.setdefault(inv.customer_id, []).append(inv)

        # To ensure at least one multi-invoice payment occurs when n_pay >= 2 and
        # any customer has >= 2 invoices, we prioritize selecting at least 2 invoices
        # from that customer into to_pay_invoices.
        to_pay_set = set()
        multi_customer_id = None
        if n_pay >= 2:
            for cust_id, invs in by_customer_all.items():
                if len(invs) >= 2:
                    multi_customer_id = cust_id
                    to_pay_set.add(invs[0].id)
                    to_pay_set.add(invs[1].id)
                    break

        remaining_invoices = [inv for inv in confirmed_outstanding if inv.id not in to_pay_set]
        rng.shuffle(remaining_invoices)
        needed = n_pay - len(to_pay_set)
        if needed > 0:
            for inv in remaining_invoices[:needed]:
                to_pay_set.add(inv.id)

        to_pay_invoices = [inv for inv in confirmed_outstanding if inv.id in to_pay_set]
        leave_unpaid = [inv for inv in confirmed_outstanding if inv.id not in to_pay_set]

        payments_ok = 0
        payment_failures = 0
        partial_payments_count = 0
        full_payments_count = 0
        multi_payments_count = 0

        # Group to_pay_invoices by customer
        by_customer: dict = {}
        for inv in to_pay_invoices:
            by_customer.setdefault(inv.customer_id, []).append(inv)

        multi_done = False
        for cust_id, inv_list in by_customer.items():
            # Perform multi-invoice payment if >= 2 invoices and (not multi_done or rng.random() < 0.3)
            if len(inv_list) >= 2 and (not multi_done or rng.random() < 0.3):
                # Take at least 2 (up to 5) invoices for this multi payment
                chunk_size = min(len(inv_list), 5)
                multi_chunk = inv_list[:chunk_size]
                inv_list = inv_list[chunk_size:]

                allocs = []
                total_amt = Decimal("0.00")
                for inv in multi_chunk:
                    inv.refresh_from_db()
                    outstanding = inv.total - inv.amount_paid
                    if outstanding > Decimal("0.00") and inv.status == "confirmed":
                        allocs.append({
                            "invoice_id": inv.id,
                            "amount": outstanding,
                        })
                        total_amt += outstanding

                if allocs:
                    try:
                        record_payment(
                            customer_id=cust_id,
                            method=rng.choice(["card", "bank_transfer", "upi", "cash"]),
                            amount=total_amt,
                            payment_date=target_date,
                            allocations=allocs,
                            note=f"seed_billing multi-invoice payment ({len(allocs)} invoices)",
                            recorded_by=admin_user,
                        )
                        payments_ok += 1
                        multi_payments_count += 1
                        multi_done = True
                    except Exception as exc:
                        payment_failures += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"  [WARN] multi-invoice payment for customer {cust_id} failed: {exc}"
                            )
                        )
                        # Fall back: try individually
                        for inv in multi_chunk:
                            ok, is_part = self._pay_single(
                                inv, rng, admin_user, target_date, partial_ratio,
                                record_payment,
                            )
                            if ok:
                                payments_ok += 1
                                if is_part:
                                    partial_payments_count += 1
                                else:
                                    full_payments_count += 1
                            else:
                                payment_failures += 1

            # Pay remaining individual invoices for this customer
            for inv in inv_list:
                ok, is_part = self._pay_single(
                    inv, rng, admin_user, target_date, partial_ratio,
                    record_payment,
                )
                if ok:
                    payments_ok += 1
                    if is_part:
                        partial_payments_count += 1
                    else:
                        full_payments_count += 1
                else:
                    payment_failures += 1

        self.stdout.write(f"  confirmed w/ outstanding: {len(confirmed_outstanding)}")
        self.stdout.write(f"  to pay:           {len(to_pay_invoices)}")
        self.stdout.write(f"  payments OK:      {payments_ok}")
        self.stdout.write(f"    - multi-invoice:{multi_payments_count}")
        self.stdout.write(f"    - full:         {full_payments_count}")
        self.stdout.write(f"    - partial:      {partial_payments_count}")
        self.stdout.write(f"  failures:         {payment_failures}")
        self.stdout.write(f"  left unpaid:      {len(leave_unpaid)}")

        # ------------------------------------------------------------------ #
        # Step 4: Summary stats using selectors
        # ------------------------------------------------------------------ #
        from apps.billing import selectors as billing_selectors
        from apps.payments import selectors as payments_selectors
        from apps.payments.models import Payment

        self.stdout.write("\n--- Final stats ---")
        counts = billing_selectors.invoice_counts_by_status()
        for k, v in counts.items():
            self.stdout.write(f"  invoices[{k}]: {v}")
        self.stdout.write(f"  payments total: {Payment.objects.count()}")
        total_outstanding = billing_selectors.outstanding_total()
        total_overdue = billing_selectors.overdue_total()
        self.stdout.write(f"  outstanding:    {total_outstanding}")
        self.stdout.write(f"  overdue:        {total_overdue}")

        try:
            rev = payments_selectors.revenue_between(
                start=date(2000, 1, 1),
                end=date(2099, 12, 31),
            )
            self.stdout.write(f"  revenue:        {rev}")
        except Exception as exc:
            self.stdout.write(f"  revenue:        (error: {exc})")

        self.stdout.write(self.style.SUCCESS("\nDone."))

    def _pay_single(self, inv, rng, admin_user, target_date, partial_ratio, record_payment):
        """Pay a single invoice (fully or partially). Returns (success: bool, is_partial: bool)."""
        inv.refresh_from_db()
        outstanding = inv.total - inv.amount_paid
        if outstanding <= Decimal("0.00") or inv.status != "confirmed":
            return True, False  # already settled, not a failure

        is_partial = (rng.random() < partial_ratio) and (outstanding > Decimal("0.05"))
        if is_partial:
            # Random fraction between 20% and 80%
            factor = Decimal(str(round(rng.uniform(0.20, 0.80), 2)))
            pay_amount = (outstanding * factor).quantize(Decimal("0.01"))
            if pay_amount <= Decimal("0.00") or pay_amount >= outstanding:
                pay_amount = (outstanding / Decimal("2")).quantize(Decimal("0.01"))
            if pay_amount <= Decimal("0.00"):
                pay_amount = Decimal("0.01")
        else:
            pay_amount = outstanding

        try:
            record_payment(
                customer_id=inv.customer_id,
                method=rng.choice(["card", "bank_transfer", "upi", "cash"]),
                amount=pay_amount,
                payment_date=target_date,
                allocations=[{"invoice_id": inv.id, "amount": pay_amount}],
                note=f"seed_billing {'partial' if is_partial else 'full'} payment",
                recorded_by=admin_user,
            )
            return True, is_partial
        except Exception as exc:
            self.stdout.write(
                self.style.WARNING(f"  [WARN] payment for invoice {inv.id} failed: {exc}")
            )
            return False, False
