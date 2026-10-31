from django.contrib import admin
from django.urls import include, path

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("admin/", admin.site.urls),

    # Authentication
    path("api/auth/", include("apps.accounts.urls")),

    # Subscriptions & Sales
    path("api/subscriptions/", include("apps.subscriptions.urls")),
    path("api/sales/", include("apps.sales.urls")),

    # Billing & Payments
    path("api/billing/", include("apps.billing.urls")),
    path("api/payments/", include("apps.payments.urls")),

    # API documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]