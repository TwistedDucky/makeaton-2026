import calendar
from datetime import date, timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Subscription, SubscriptionLine
from apps.sales.models import Quotation


def add_months(source_date: date, months: int) -> date:
    """Safely adds months to a date without exceeding month boundaries."""
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def calculate_period_end(start_date: date, billing_period: str) -> date:
    """Calculates the end date of a billing cycle (inclusive)."""
    period = (billing_period or "").lower()
    if period == "daily":
        return start_date
    elif period == "weekly":
        return start_date + timedelta(days=6)
    elif period == "monthly":
        # 1 month forward minus 1 day for inclusive end date
        next_month = add_months(start_date, 1)
        return next_month - timedelta(days=1)
    elif period == "yearly":
        try:
            next_year = start_date.replace(year=start_date.year + 1)
        except ValueError:
            next_year = start_date.replace(year=start_date.year + 1, day=28)
        return next_year - timedelta(days=1)
    else:
        # Default fallback to 30 days
        return start_date + timedelta(days=29)


# ==============================================================================
# STATE MACHINE PIPELINE
# Lifecycle: DRAFT -> QUOTATION -> CONFIRMED -> ACTIVE -> CLOSED
# ==============================================================================

VALID_TRANSITIONS = {
    Subscription.Status.DRAFT: [
        Subscription.Status.QUOTATION,
        Subscription.Status.CONFIRMED,
        Subscription.Status.CLOSED,
    ],
    Subscription.Status.QUOTATION: [
        Subscription.Status.CONFIRMED,
        Subscription.Status.CLOSED,
    ],
    Subscription.Status.CONFIRMED: [
        Subscription.Status.ACTIVE,
        Subscription.Status.CLOSED,
    ],
    Subscription.Status.ACTIVE: [
        Subscription.Status.CLOSED,
    ],
    Subscription.Status.CLOSED: [],  # Terminal state
}


@transaction.atomic
def transition_subscription(subscription: Subscription, target_status: str, reason: str = "") -> Subscription:
    """
    Strict state machine transition function.
    Validates rules, triggers lifecycle hooks, and updates the subscription.
    """
    current_status = subscription.status

    if current_status == target_status:
        return subscription

    allowed_targets = VALID_TRANSITIONS.get(current_status, [])
    if target_status not in allowed_targets:
        raise ValidationError(
            f"Invalid state transition: Cannot move subscription from {current_status} to {target_status}."
        )

    # 1. Transitioning to QUOTATION
    if target_status == Subscription.Status.QUOTATION:
        if not subscription.lines.exists():
            raise ValidationError("Cannot move to Quotation state without any product lines.")

    # 2. Transitioning to CONFIRMED
    elif target_status == Subscription.Status.CONFIRMED:
        if not subscription.lines.exists():
            raise ValidationError("Cannot confirm a subscription with no product lines.")
        if subscription.total_amount <= 0:
            subscription.recalculate_totals()

    # 3. Transitioning to ACTIVE
    elif target_status == Subscription.Status.ACTIVE:
        today = timezone.now().date()
        start = subscription.start_date or today
        subscription.start_date = start

        # Initialize billing schedule for Member 4
        billing_period = subscription.plan.billing_period
        subscription.current_period_start = start
        subscription.current_period_end = calculate_period_end(start, billing_period)
        subscription.next_billing_date = start  # First billing occurs on or immediately after start

    # 4. Transitioning to CLOSED
    elif target_status == Subscription.Status.CLOSED:
        if reason:
            subscription.cancellation_reason = reason
        if not subscription.expiry_date:
            subscription.expiry_date = timezone.now().date()

    subscription.status = target_status
    subscription.save()
    return subscription


# ==============================================================================
# QUOTATION CONVERSION
# ==============================================================================

@transaction.atomic
def convert_quotation_to_subscription(quotation_id: int, start_date: date = None) -> Subscription:
    """
    Converts an accepted or valid Quotation into a Subscription.
    Clones product lines and associates them with the contract.
    """
    quotation = Quotation.objects.select_related("customer", "plan").prefetch_related("lines").get(pk=quotation_id)

    if quotation.status == Quotation.Status.CONVERTED:
        existing = quotation.converted_subscriptions.first()
        if existing:
            return existing

    if quotation.is_expired():
        raise ValidationError("Cannot convert an expired quotation.")

    sub_start = start_date or timezone.now().date()

    subscription = Subscription.objects.create(
        customer=quotation.customer,
        plan=quotation.plan,
        status=Subscription.Status.CONFIRMED,
        start_date=sub_start,
        payment_terms=quotation.payment_terms,
        quotation=quotation,
        notes=f"Converted from quotation {quotation.quotation_number}. {quotation.notes}".strip(),
    )

    for q_line in quotation.lines.all():
        SubscriptionLine.objects.create(
            subscription=subscription,
            product=q_line.product,
            variant=q_line.variant,
            quantity=q_line.quantity,
            unit_price=q_line.unit_price,
            taxes=q_line.taxes,
        )

    subscription.recalculate_totals()

    quotation.status = Quotation.Status.CONVERTED
    quotation.save(update_fields=["status", "updated_at"])

    return subscription


# ==============================================================================
# MEMBER 4 INVOICE GENERATION INTEGRATIONS
# ==============================================================================

def get_due_subscriptions(target_date: date = None) -> list[dict]:
    """
    Returns active subscriptions due for billing on or before target_date.
    Exact contract shape requested by Member 4.
    """
    eval_date = target_date or timezone.now().date()
    due_subs = (
        Subscription.objects.filter(
            status=Subscription.Status.ACTIVE,
            next_billing_date__lte=eval_date,
        )
        .select_related("customer", "plan")
        .prefetch_related("lines__product", "lines__variant")
    )

    results = []
    for sub in due_subs:
        lines_data = []
        for line in sub.lines.all():
            variant_str = f" - {line.variant.value}" if line.variant else ""
            lines_data.append({
                "product_id": line.product_id,
                "product_name": f"{line.product.name}{variant_str}",
                "variant_id": line.variant_id,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "tax_id": line.product.tax_id,
            })

        period_start = sub.current_period_start or sub.start_date or eval_date
        period_end = sub.current_period_end or calculate_period_end(period_start, sub.plan.billing_period)

        results.append({
            "id": sub.id,
            "customer_id": sub.customer_id,
            "period_start": period_start,
            "period_end": period_end,
            "lines": lines_data,
        })

    return results


@transaction.atomic
def advance_next_billing_date(subscription_id: int) -> dict:
    """
    Advances a subscription's billing cycle after Member 4 successfully generates an invoice.
    Idempotent and safe to call.
    Checks auto-close rule against expiry_date.
    """
    subscription = Subscription.objects.select_related("plan").get(pk=subscription_id)

    if subscription.status != Subscription.Status.ACTIVE:
        return {
            "subscription_id": subscription.id,
            "next_billing_date": subscription.next_billing_date,
            "status": subscription.status,
        }

    billing_period = subscription.plan.billing_period
    current_end = subscription.current_period_end or timezone.now().date()
    new_period_start = current_end + timedelta(days=1)
    new_period_end = calculate_period_end(new_period_start, billing_period)

    subscription.last_billed_date = timezone.now().date()
    subscription.current_period_start = new_period_start
    subscription.current_period_end = new_period_end
    subscription.next_billing_date = new_period_start

    # Check plan auto-close rule:
    # If the plan is configured to auto-close and the contract has expired
    if subscription.plan.auto_close and subscription.expiry_date:
        if subscription.next_billing_date > subscription.expiry_date:
            subscription.status = Subscription.Status.CLOSED
            subscription.cancellation_reason = "Plan automatically closed upon reaching expiry date."

    subscription.save()

    return {
        "subscription_id": subscription.id,
        "next_billing_date": subscription.next_billing_date,
        "status": subscription.status,
    }


@transaction.atomic
def renew_subscription(subscription_id: int) -> Subscription:
    """
    Extends the subscription contract period by one billing period if renewable.
    Enforces plan.renewable flag from catalog Plan settings.
    """
    subscription = Subscription.objects.select_related("plan").get(pk=subscription_id)
    if not subscription.plan.renewable:
        raise ValidationError("This subscription plan is not configured for automatic renewal.")
    if subscription.status != Subscription.Status.ACTIVE:
        raise ValidationError("Only active subscriptions can be renewed.")

    current_expiry = subscription.expiry_date or subscription.current_period_end or timezone.now().date()
    new_period_start = current_expiry + timedelta(days=1)
    new_expiry = calculate_period_end(new_period_start, subscription.plan.billing_period)

    subscription.expiry_date = new_expiry
    subscription.save(update_fields=["expiry_date", "updated_at"])
    return subscription

