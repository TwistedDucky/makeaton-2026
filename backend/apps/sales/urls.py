from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import QuotationTemplateViewSet, QuotationViewSet

router = DefaultRouter()
router.register(r"templates", QuotationTemplateViewSet, basename="quotation-template")
router.register(r"quotations", QuotationViewSet, basename="quotation")

urlpatterns = [
    path("", include(router.urls)),
]
