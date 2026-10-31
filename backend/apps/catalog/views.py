from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.pagination import StandardPagination
from .filters import DiscountFilter, PlanFilter, ProductFilter, TaxFilter
from .models import Discount, Plan, Product, Tax
from .permissions import IsAdminOrReadOnly, IsAdminWriteStaffRead
from .selectors import (
    all_discounts,
    all_taxes,
    discount_usages,
    visible_plans,
    visible_products,
    visible_variants,
)
from .serializers import (
    DiscountSerializer,
    DiscountUsageSerializer,
    PlanSerializer,
    ProductSerializer,
    ProductVariantSerializer,
    TaxSerializer,
)

DeactivateResponseSerializer = inline_serializer(
    name="DeactivateResponse",
    fields={
        "success": serializers.BooleanField(default=True),
        "message": serializers.CharField(default="Deactivated"),
    },
)

variant_id_parameter = OpenApiParameter(
    name="variant_id",
    type=int,
    location=OpenApiParameter.PATH,
    description="The ID of the product variant.",
)


class SoftDeleteModelViewSet(viewsets.ModelViewSet):
    """
    Base viewset providing soft deletion via is_active=False.
    Always returns HTTP 200 with JSON on destroy, never 204.
    """

    pagination_class = StandardPagination

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        return Response(
            {"success": True, "message": "Deactivated"},
            status=status.HTTP_200_OK,
        )


class ProductViewSet(SoftDeleteModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_class = ProductFilter
    search_fields = ["name", "type"]
    ordering_fields = ["name", "sales_price", "id"]
    ordering = ["name"]

    def get_queryset(self):
        return visible_products(self.request.user)

    @extend_schema(
        methods=["GET"],
        responses={200: ProductVariantSerializer(many=True)},
        summary="List variants of a product",
    )
    @extend_schema(
        methods=["POST"],
        request=ProductVariantSerializer,
        responses={201: ProductVariantSerializer},
        summary="Create a variant for a product",
    )
    @action(detail=True, methods=["get", "post"], url_path="variants")
    def variants(self, request, pk=None):
        product = self.get_object()
        if request.method.lower() == "get":
            queryset = visible_variants(product, request.user)
            serializer = ProductVariantSerializer(
                queryset,
                many=True,
                context=self.get_serializer_context(),
            )
            return Response(serializer.data)

        data = (
            request.data.copy()
            if hasattr(request.data, "copy")
            else dict(request.data)
        )
        data["product"] = product.id
        serializer = ProductVariantSerializer(
            data=data,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(product=product)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        methods=["GET"],
        parameters=[variant_id_parameter],
        responses={200: ProductVariantSerializer},
        summary="Retrieve a product variant",
    )
    @extend_schema(
        methods=["PUT"],
        parameters=[variant_id_parameter],
        request=ProductVariantSerializer,
        responses={200: ProductVariantSerializer},
        summary="Update a product variant",
    )
    @extend_schema(
        methods=["PATCH"],
        parameters=[variant_id_parameter],
        request=ProductVariantSerializer,
        responses={200: ProductVariantSerializer},
        summary="Partially update a product variant",
    )
    @extend_schema(
        methods=["DELETE"],
        parameters=[variant_id_parameter],
        responses={200: DeactivateResponseSerializer},
        summary="Deactivate a product variant",
    )
    @action(
        detail=True,
        methods=["get", "put", "patch", "delete"],
        url_path=r"variants/(?P<variant_id>[^/.]+)",
    )
    def variant_detail(self, request, pk=None, variant_id=None):
        product = self.get_object()
        if request.method.lower() == "get":
            variant = get_object_or_404(
                visible_variants(product, request.user),
                id=variant_id,
            )
            serializer = ProductVariantSerializer(
                variant,
                context=self.get_serializer_context(),
            )
            return Response(serializer.data)

        variant = get_object_or_404(product.variants.all(), id=variant_id)

        if request.method.lower() == "delete":
            variant.is_active = False
            variant.save(update_fields=["is_active"])
            return Response(
                {"success": True, "message": "Deactivated"},
                status=status.HTTP_200_OK,
            )

        partial = request.method.lower() == "patch"
        data = (
            request.data.copy()
            if hasattr(request.data, "copy")
            else dict(request.data)
        )
        data["product"] = product.id
        serializer = ProductVariantSerializer(
            variant,
            data=data,
            partial=partial,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(product=product)
        return Response(serializer.data)


class PlanViewSet(SoftDeleteModelViewSet):
    serializer_class = PlanSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_class = PlanFilter
    search_fields = ["name"]
    ordering_fields = ["name", "price", "id"]
    ordering = ["name"]

    def get_queryset(self):
        return visible_plans(self.request.user)


class TaxViewSet(SoftDeleteModelViewSet):
    serializer_class = TaxSerializer
    permission_classes = [IsAdminWriteStaffRead]
    filterset_class = TaxFilter
    search_fields = ["name"]
    ordering_fields = ["name", "rate", "id"]
    ordering = ["name"]

    def get_queryset(self):
        return all_taxes()


class DiscountViewSet(SoftDeleteModelViewSet):
    serializer_class = DiscountSerializer
    permission_classes = [IsAdminWriteStaffRead]
    filterset_class = DiscountFilter
    search_fields = ["name"]
    ordering_fields = ["name", "value", "id"]
    ordering = ["name"]

    def get_queryset(self):
        return all_discounts()

    @extend_schema(
        responses={200: DiscountUsageSerializer(many=True)},
        summary="List usages of a discount",
    )
    @action(detail=True, methods=["get"], url_path="usage")
    def usage(self, request, pk=None):
        discount = self.get_object()
        usages = discount_usages(discount)
        page = self.paginate_queryset(usages)
        if page is not None:
            serializer = DiscountUsageSerializer(
                page,
                many=True,
                context=self.get_serializer_context(),
            )
            return self.get_paginated_response(serializer.data)
        serializer = DiscountUsageSerializer(
            usages,
            many=True,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)
