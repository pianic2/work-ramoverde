from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView
from rest_framework.permissions import IsAuthenticated

from apps.core.health import LivenessView, ReadinessView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/live", LivenessView.as_view(), name="health-live"),
    path("api/v1/health/ready", ReadinessView.as_view(), name="health-ready"),
    path("api/v1/", include("apps.accounts.urls")),
    path(
        "api/schema/",
        SpectacularAPIView.as_view(permission_classes=[IsAuthenticated]),
        name="schema",
    ),
]
