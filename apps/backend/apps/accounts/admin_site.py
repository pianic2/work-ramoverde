"""Django admin restricted to technical superusers holding a tracked staff session.

Django admin is mounted at /django-admin/ and never authenticates anyone itself: its
password login form is replaced by a redirect to the staff sign-in flow, so it cannot be
used to bypass the staff authentication requirements (MFA, password policy).
"""

from typing import Any

from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from .auth_sessions import active_web_session


class StaffAdminSite(admin.AdminSite):
    site_header = "RamoVerde — amministrazione tecnica"
    site_title = "RamoVerde admin tecnico"

    def has_permission(self, request: HttpRequest) -> bool:
        user = request.user
        if not (user.is_active and user.is_staff and user.is_superuser):
            return False
        return active_web_session(request) is not None

    def login(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:
        return HttpResponseRedirect(settings.STAFF_LOGIN_URL)

    def password_change(  # type: ignore[override]
        self, request: HttpRequest, extra_context: Any = None
    ) -> HttpResponse:
        return HttpResponseRedirect(settings.STAFF_LOGIN_URL)
