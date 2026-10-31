from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Quotation, QuotationTemplate
from .serializers import (
    CreateFromTemplateSerializer,
    QuotationSerializer,
    QuotationTemplateSerializer,
)
from .services import (
    accept_quotation,
    create_quotation_from_template,
    decline_quotation,
    send_quotation,
)
from apps.subscriptions.serializers import SubscriptionSerializer
from apps.subscriptions.services import convert_quotation_to_subscription
from common.pagination import StandardPagination
from common.permissions import IsStaffOrAdmin


class QuotationTemplateViewSet(viewsets.ModelViewSet):
    queryset = QuotationTemplate.objects.select_related("plan").prefetch_related("lines__product").all()
    serializer_class = QuotationTemplateSerializer
    pagination_class = StandardPagination
    permission_classes = [IsAuthenticated]
    filterset_fields = ["is_active", "plan"]
    search_fields = ["name", "description"]


class QuotationViewSet(viewsets.ModelViewSet):
    serializer_class = QuotationSerializer
    pagination_class = StandardPagination
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "plan", "template"]
    search_fields = ["quotation_number", "customer__email"]
    ordering_fields = ["created_at", "valid_until", "total_amount"]
    ordering = ["-created_at"]

    def get_queryset(self):
        user = self.request.user
        qs = (
            Quotation.objects.select_related("customer", "sales_rep", "plan", "template")
            .prefetch_related("lines__product", "lines__variant")
            .all()
        )
        if getattr(user, "role", None) == "CUSTOMER":
            return qs.filter(customer=user)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if getattr(user, "role", None) in ["STAFF", "ADMIN"]:
            serializer.save(sales_rep=user)
        else:
            serializer.save(customer=user)

    @action(detail=False, methods=["post"], permission_classes=[IsStaffOrAdmin], url_path="from-template")
    def from_template(self, request):
        """Create a new Quotation from a QuotationTemplate."""
        serializer = CreateFromTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        template_id = serializer.validated_data["template_id"]
        customer_id = serializer.validated_data.get("customer_id")
        notes = serializer.validated_data.get("notes", "")

        if not customer_id:
            return Response({"error": "customer_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            quotation = create_quotation_from_template(
                template_id=template_id,
                customer_id=customer_id,
                sales_rep_id=request.user.id,
                notes=notes,
            )
            return Response(QuotationSerializer(quotation).data, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="send")
    def send(self, request, pk=None):
        try:
            quotation = send_quotation(pk)
            return Response(QuotationSerializer(quotation).data)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="accept")
    def accept(self, request, pk=None):
        try:
            quotation = accept_quotation(pk)
            return Response(QuotationSerializer(quotation).data)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="decline")
    def decline(self, request, pk=None):
        reason = request.data.get("reason", "")
        try:
            quotation = decline_quotation(pk, reason=reason)
            return Response(QuotationSerializer(quotation).data)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="convert")
    def convert(self, request, pk=None):
        """Convert this accepted quotation into an active/confirmed subscription."""
        try:
            subscription = convert_quotation_to_subscription(pk)
            return Response(SubscriptionSerializer(subscription).data, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
