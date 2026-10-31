from rest_framework.routers import DefaultRouter

from .views import DiscountViewSet, PlanViewSet, ProductViewSet, TaxViewSet

router = DefaultRouter()
router.register(r"products", ProductViewSet, basename="product")
router.register(r"plans", PlanViewSet, basename="plan")
router.register(r"taxes", TaxViewSet, basename="tax")
router.register(r"discounts", DiscountViewSet, basename="discount")

urlpatterns = router.urls
