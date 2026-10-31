"""
URL routing for the payments app.
"""
from rest_framework.routers import DefaultRouter

from .views import PaymentViewSet

app_name = "payments"

router = DefaultRouter()
router.register(r"", PaymentViewSet, basename="payment")

urlpatterns = router.urls
