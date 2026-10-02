"""DRF authentication classes for staff APIs.

A request is authenticated only when it is backed by an active `UserSession`; the
`UserSession` is exposed as `request.auth` so permissions can inspect it.
"""

from typing import Any

from drf_spectacular.authentication import SessionScheme
from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication

from .auth_sessions import SESSION_CLAIM, active_mobile_session, active_web_session, touch


class StaffSessionAuthentication(SessionAuthentication):
    """Django session cookie + CSRF, accepted only for a tracked, unrevoked web session."""

    def authenticate(self, request: Request) -> tuple[Any, Any] | None:
        tracked = active_web_session(request._request)
        if tracked is None:
            return None
        self.enforce_csrf(request)
        touch(tracked)
        return (tracked.user, tracked)


class StaffJWTAuthentication(JWTAuthentication):
    """Bearer access token whose `sid` claim names an active mobile session."""

    def authenticate(self, request: Request) -> tuple[Any, Any] | None:
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        tracked = active_mobile_session(token.get(SESSION_CLAIM), user.pk)
        if tracked is None or not user.is_active:
            raise AuthenticationFailed("Sessione non valida o revocata.", code="session_revoked")
        touch(tracked)
        return (tracked.user, tracked)


class StaffSessionScheme(SessionScheme):  # type: ignore[no-untyped-call]
    target_class = "apps.accounts.authentication.StaffSessionAuthentication"


class StaffJWTScheme(SimpleJWTScheme):  # type: ignore[no-untyped-call]
    target_class = "apps.accounts.authentication.StaffJWTAuthentication"
