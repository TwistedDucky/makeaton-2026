from datetime import date
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Subscription
from .serializers import (
    SubscriptionSerializer,
    SubscriptionTransitionSerializer,
)
from .services import (
    advance_next_billing_date,
    get_due_subscriptions,
    transition_subscription,
)
from common.pagination import StandardPagination
from common.permissions import IsStaffOrAdmin


class SubscriptionViewSet(viewsets.ModelViewSet):
    serializer_class = SubscriptionSerializer
    pagination_class = StandardPagination
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "payment_terms", "plan"]
    search_fields = ["subscription_number", "customer__email"]
    ordering_fields = ["created_at", "start_date", "total_amount", "next_billing_date"]
    ordering = ["-created_at"]

    def get_queryset(self):
        user = self.request.user
        qs = (
            Subscription.objects.select_related("customer", "plan")
            .prefetch_related("lines__product", "lines__variant")
            .all()
        )
        # If user is a customer, restrict to only their own subscriptions
        if getattr(user, "role", None) == "CUSTOMER":
            return qs.filter(customer=user)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        # If customer is creating, auto-assign customer
        if getattr(user, "role", None) == "CUSTOMER":
            serializer.save(customer=user)
        else:
            serializer.save()

    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request, pk=None):
        """Move subscription through its lifecycle pipeline."""
        subscription = self.get_object()
        serializer = SubscriptionTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target_status = serializer.validated_data["target_status"]
        reason = serializer.validated_data.get("reason", "")

        try:
            updated = transition_subscription(subscription, target_status, reason)
            return Response(SubscriptionSerializer(updated).data)
        except ValidationError as e:
            return Response(
                {"success": False, "message": str(e.message if hasattr(e, 'message') else e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["get"], permission_classes=[IsStaffOrAdmin], url_path="due-for-billing")
    def due_for_billing(self, request):
        """API endpoint to query subscriptions due on target_date (used by Member 4)."""
        target_str = request.query_params.get("target_date")
        if target_str:
            try:
                target_date = date.fromisoformat(target_str)
            except ValueError:
                return Response({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400)
        else:
            target_date = timezone.now().date()

        due_list = get_due_subscriptions(target_date)
        return Response({"success": True, "count": len(due_list), "data": due_list})

    @action(detail=True, methods=["post"], permission_classes=[IsStaffOrAdmin], url_path="advance-billing")
    def advance_billing(self, request, pk=None):
        """Advances the billing cycle after an invoice is created."""
        subscription = self.get_object()
        result = advance_next_billing_date(subscription.id)
        return Response({"success": True, "data": result})
