from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from apps.accounts.permissions import IsStaffUser
from apps.core.health import LivenessView, ReadinessView

urlpatterns = [
    # Technical superuser admin only; the staff backoffice is the React app at web /admin/*.
    path("django-admin/", admin.site.urls),
    path("api/v1/health/live", LivenessView.as_view(), name="health-live"),
    path("api/v1/health/ready", ReadinessView.as_view(), name="health-ready"),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.media.urls")),
    path("api/v1/", include("apps.cms.urls")),
    path(
        "api/schema/",
        SpectacularAPIView.as_view(permission_classes=[IsStaffUser]),
        name="schema",
    ),
]
