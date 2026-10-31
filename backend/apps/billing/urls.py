"""
URL routing for the billing app.
"""
from rest_framework.routers import DefaultRouter

from .views import InvoiceViewSet

app_name = "billing"

router = DefaultRouter()
router.register(r"invoices", InvoiceViewSet, basename="invoice")

urlpatterns = router.urls
