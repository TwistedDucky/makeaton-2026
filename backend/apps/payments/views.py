"""
Views and API endpoints for payments and allocations.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated

from apps.billing.api_utils import (
    error_response,
    handle_billing_errors,
    success_response,
    validation_error_to_response,
)
from common.pagination import StandardPagination
from common.permissions import IsStaffOrAdmin

from . import services
from .models import Payment
from .serializers import PaymentCreateInputSerializer, PaymentSerializer

User = get_user_model()


class PaymentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    API endpoint for payments:
    - GET /api/payments/ (list)
    - GET /api/payments/{id}/ (detail)
    - POST /api/payments/ (record payment)
    No PUT, PATCH, or DELETE (returns 405 Method Not Allowed).
    """

    lookup_value_regex = r"\d+"
    pagination_class = StandardPagination
    filter_backends = [OrderingFilter]
    ordering_fields = ["payment_date", "amount", "created_at"]
    ordering = ["-payment_date"]
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), IsStaffOrAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Payment.objects.none()

        qs = (
            Payment.objects.select_related("customer", "recorded_by")
            .prefetch_related("allocations__invoice")
            .all()
        )

        if getattr(user, "role", None) == "CUSTOMER":
            qs = qs.filter(customer=user)

        if self.action == "list":
            qs = self._apply_filters(qs, self.request)

        return qs

    def _apply_filters(self, qs, request):
        params = request.query_params
        user = request.user

        # 1. Customer filter (staff/admin only, ignored for customers)
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

        # 2. Method filter
        method_param = params.get("method")
        if method_param is not None:
            m_val = method_param.lower().strip()
            if m_val not in Payment.Method.values:
                raise DjangoValidationError(
                    {
                        "method": [
                            f"Invalid payment method '{method_param}'. Allowed: {', '.join(Payment.Method.values)}."
                        ]
                    }
                )
            qs = qs.filter(method=m_val)

        # 3. Date range filters
        date_from = params.get("date_from")
        if date_from:
            try:
                d_from = date.fromisoformat(date_from)
                qs = qs.filter(payment_date__gte=d_from)
            except (ValueError, TypeError):
                raise DjangoValidationError(
                    {
                        "date_from": [
                            f"Invalid date format '{date_from}'. Expected YYYY-MM-DD."
                        ]
                    }
                )

        date_to = params.get("date_to")
        if date_to:
            try:
                d_to = date.fromisoformat(date_to)
                qs = qs.filter(payment_date__lte=d_to)
            except (ValueError, TypeError):
                raise DjangoValidationError(
                    {
                        "date_to": [
                            f"Invalid date format '{date_to}'. Expected YYYY-MM-DD."
                        ]
                    }
                )

        # 4. Invoice filter (integer id OR invoice number string)
        invoice_param = params.get("invoice")
        if invoice_param:
            inv_str = invoice_param.strip()
            if inv_str.isdigit():
                inv_id = int(inv_str)
                qs = qs.filter(
                    Q(allocations__invoice_id=inv_id)
                    | Q(allocations__invoice__number=inv_str)
                ).distinct()
            else:
                qs = qs.filter(allocations__invoice__number=inv_str).distinct()

        # 5. Optional search
        search_query = params.get("search")
        if search_query and search_query.strip():
            term = search_query.strip()
            if getattr(user, "role", None) in ["STAFF", "ADMIN"]:
                qs = qs.filter(
                    Q(note__icontains=term) | Q(customer__email__icontains=term)
                ).distinct()
            else:
                qs = qs.filter(note__icontains=term).distinct()

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

    @handle_billing_errors
    def create(self, request, *args, **kwargs):
        serializer = PaymentCreateInputSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        customer_id = data["customer"]
        if not User.objects.filter(id=customer_id).exists():
            raise DjangoValidationError(
                {"customer": [f"Customer with id {customer_id} does not exist."]}
            )

        # Resolve allocations
        from apps.billing.models import Invoice

        raw_allocs = data["allocations"]
        mapped_allocations = []
        for alloc in raw_allocs:
            raw_inv = alloc["invoice"]
            alloc_amt = alloc["amount"]

            inv_obj = None
            if isinstance(raw_inv, int) and not isinstance(raw_inv, bool):
                inv_obj = Invoice.objects.filter(id=raw_inv).first()
            elif isinstance(raw_inv, str):
                s = raw_inv.strip()
                inv_obj = Invoice.objects.filter(number=s).first()
                if not inv_obj and s.isdigit():
                    inv_obj = Invoice.objects.filter(id=int(s)).first()

            if not inv_obj:
                raise DjangoValidationError(
                    {"allocations": [f"Invoice '{raw_inv}' not found."]}
                )

            mapped_allocations.append(
                {
                    "invoice_id": inv_obj.id,
                    "amount": alloc_amt,
                }
            )

        payment = services.record_payment(
            customer_id=customer_id,
            method=data["method"],
            amount=data["amount"],
            payment_date=data.get("payment_date"),
            allocations=mapped_allocations,
            note=data.get("note", ""),
            recorded_by=request.user,
        )

        payment = (
            Payment.objects.select_related("customer", "recorded_by")
            .prefetch_related("allocations__invoice")
            .get(id=payment.id)
        )
        return success_response(
            data=PaymentSerializer(payment).data,
            message="Payment recorded successfully.",
            status_code=status.HTTP_201_CREATED,
        )
