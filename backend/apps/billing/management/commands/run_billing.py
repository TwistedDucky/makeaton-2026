"""
Management command to run recurring billing generation.

Scheduling Note:
Configure an external scheduler or cron job to execute this command periodically.
Example crontab entry (run daily at midnight UTC):
0 0 * * * docker compose exec -T backend python manage.py run_billing

Manual command line execution example:
docker compose exec backend python manage.py run_billing
docker compose exec backend python manage.py run_billing --date 2026-10-31 --json
"""

from datetime import date
import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.billing.services import generate_invoices, summary_as_dict


class Command(BaseCommand):
    help = "Generate recurring draft invoices for due subscriptions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Target date for invoice generation (YYYY-MM-DD). Defaults to today.",
        )
        parser.add_argument(
            "--max-periods",
            type=int,
            default=24,
            help="Maximum billing periods to advance per subscription (default: 24, must be >= 1).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output summary as JSON only.",
        )

    def handle(self, *args, **options):
        date_str = options.get("date")
        if date_str is not None:
            try:
                target_date = date.fromisoformat(date_str)
            except (ValueError, TypeError) as exc:
                raise CommandError(
                    f"Invalid date format '{date_str}'. Expected YYYY-MM-DD."
                ) from exc
        else:
            target_date = timezone.localdate()

        max_periods = options.get("max_periods", 24)
        if max_periods is None or max_periods < 1:
            raise CommandError(f"--max-periods must be >= 1, got {max_periods}.")

        is_json = options.get("json", False)

        summary = generate_invoices(
            target_date=target_date,
            max_periods_per_subscription=max_periods,
        )

        summary_dict = summary_as_dict(summary)

        if is_json:
            self.stdout.write(json.dumps(summary_dict))
        else:
            self.stdout.write(f"created: {summary.created}")
            self.stdout.write(f"skipped_existing: {summary.skipped_existing}")
            self.stdout.write(f"advanced: {summary.advanced}")
            self.stdout.write(f"capped: {summary.capped}")
            for err in summary_dict["errors"]:
                self.stdout.write(
                    f"error: subscription {err['subscription_id']}, period {err['period_start']}: {err['message']}"
                )

        if summary.errors:
            raise CommandError(
                f"Billing run completed with {len(summary.errors)} error(s)."
            )

