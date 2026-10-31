"""
Views and API endpoints for billing (invoices).
"""
from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import F, Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated

from common.pagination import StandardPagination
from common.permissions import IsStaffOrAdmin

from . import selectors, services
from .api_utils import (
    error_response,
    handle_billing_errors,
    success_response,
    validation_error_to_response,
)
from .models import Invoice
from .serializers import (
    GenerateInvoicesInputSerializer,
    InvoiceDetailSerializer,
    InvoiceListSerializer,
)


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for invoices:
    - GET /api/billing/invoices/ (list)
    - GET /api/billing/invoices/{id}/ (detail)
    - POST /api/billing/invoices/{id}/confirm/ (confirm draft invoice)
    - POST /api/billing/invoices/{id}/cancel/ (cancel invoice)
    - POST /api/billing/invoices/generate/ (generate recurring draft invoices)
    """

    lookup_value_regex = r"\d+"
    pagination_class = StandardPagination
    filter_backends = [OrderingFilter]
    ordering_fields = ["number", "issue_date", "due_date", "total", "created_at"]
    ordering = ["-created_at"]
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return InvoiceDetailSerializer
        return InvoiceListSerializer

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Invoice.objects.none()

        if self.action in ["retrieve", "confirm", "cancel"]:
            qs = (
                Invoice.objects.select_related("customer")
                .prefetch_related("lines", "discounts")
                .all()
            )
        else:
            qs = Invoice.objects.select_related("customer").all()

        if getattr(user, "role", None) == "CUSTOMER":
            qs = qs.filter(customer=user)

        if self.action == "list":
            qs = self._apply_filters(qs, self.request)

        return qs

    def _apply_filters(self, qs, request):
        params = request.query_params
        user = request.user

        # 1. status filter
        status_param = params.get("status")
        if status_param is not None:
            valid_statuses = {
                Invoice.Status.DRAFT,
                Invoice.Status.CONFIRMED,
                Invoice.Status.PAID,
                Invoice.Status.CANCELLED,
            }
            status_val = status_param.lower().strip()
            if status_val not in valid_statuses:
                raise DjangoValidationError(
                    {
                        "status": [
                            f"Invalid status '{status_param}'. Allowed: {', '.join(sorted(valid_statuses))}."
                        ]
                    }
                )
            qs = qs.filter(status=status_val)

        # 2. customer filter (staff/admin only, ignored for customers)
        customer_param = params.get("customer")
        if customer_param is not None and getattr(user, "role", None) in [
            "STAFF",
            "ADMIN",
        ]:
            try:
                cust_id = int(customer_param)
                qs = qs.filter(customer_id=cust_id)
            except (ValueError, TypeError):
                raise DjangoValidationError(
                    {
                        "customer": [
                            f"Invalid customer ID '{customer_param}'. Must be an integer."
                        ]
                    }
                )

        # 3. due_date_from, due_date_to (YYYY-MM-DD, 400 on bad format)
        due_from = params.get("due_date_from")
        if due_from:
            try:
                d_from = date.fromisoformat(due_from)
                qs = qs.filter(due_date__gte=d_from)
            except (ValueError, TypeError):
                raise DjangoValidationError(
                    {
                        "due_date_from": [
                            f"Invalid date format '{due_from}'. Expected YYYY-MM-DD."
                        ]
                    }
                )

        due_to = params.get("due_date_to")
        if due_to:
            try:
                d_to = date.fromisoformat(due_to)
                qs = qs.filter(due_date__lte=d_to)
            except (ValueError, TypeError):
                raise DjangoValidationError(
                    {
                        "due_date_to": [
                            f"Invalid date format '{due_to}'. Expected YYYY-MM-DD."
                        ]
                    }
                )

        # 4. overdue=true (filter directly on queryset: confirmed, due_date < localdate, total > amount_paid)
        overdue_param = params.get("overdue")
        if overdue_param is not None and overdue_param.lower() in ("true", "1"):
            qs = qs.filter(
                status=Invoice.Status.CONFIRMED,
                due_date__lt=timezone.localdate(),
                total__gt=F("amount_paid"),
            )

        # 5. search (number icontains; for staff/admin also customer email icontains; customers: number only)
        search_query = params.get("search")
        if search_query and search_query.strip():
            term = search_query.strip()
            if getattr(user, "role", None) in ["STAFF", "ADMIN"]:
                qs = qs.filter(
                    Q(number__icontains=term) | Q(customer__email__icontains=term)
                )
            else:
                qs = qs.filter(number__icontains=term)

        return qs

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except (DRFValidationError, DjangoValidationError) as exc:
            if isinstance(exc, DjangoValidationError):
                return validation_error_to_response(
                    exc, status_code=status.HTTP_400_BAD_REQUEST
                )
            detail = exc.detail
            if isinstance(detail, dict):
                errs = detail
                msg = "; ".join(
                    f"{k}: {', '.join(v) if isinstance(v, list) else v}"
                    for k, v in detail.items()
                )
            elif isinstance(detail, list):
                errs = {"non_field_errors": [str(d) for d in detail]}
                msg = "; ".join(str(d) for d in detail)
            else:
                errs = {"detail": str(detail)}
                msg = str(detail)
            return error_response(
                message=msg, errors=errs, status_code=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=["post"], permission_classes=[IsStaffOrAdmin])
    @handle_billing_errors
    def confirm(self, request, pk=None):
        result = services.confirm_invoice(int(pk))
        detail_data = InvoiceDetailSerializer(result.invoice).data
        return success_response(
            data={
                "invoice": detail_data,
                "amounts_changed": result.amounts_changed,
            },
            message="Invoice confirmed successfully.",
        )

    @action(detail=True, methods=["post"], permission_classes=[IsStaffOrAdmin])
    @handle_billing_errors
    def cancel(self, request, pk=None):
        inv = services.cancel_invoice(int(pk))
        detail_data = InvoiceDetailSerializer(inv).data
        return success_response(
            data=detail_data,
            message="Invoice cancelled successfully.",
        )

    @action(detail=False, methods=["post"], permission_classes=[IsStaffOrAdmin])
    @handle_billing_errors
    def generate(self, request):
        serializer = GenerateInvoicesInputSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        target_date = serializer.validated_data.get("target_date")

        summary = services.generate_invoices(target_date=target_date)
        return success_response(
            data=services.summary_as_dict(summary),
            message="Invoice generation completed.",
            status_code=status.HTTP_200_OK,
        )
