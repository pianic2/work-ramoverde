"""DRF authentication classes for staff APIs.

A request is authenticated only when it is backed by an active `UserSession`; the
`UserSession` is exposed as `request.auth` so permissions can inspect it.
"""

from typing import Any

from drf_spectacular.authentication import SessionScheme
from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request

from .auth_sessions import active_web_session, touch


class StaffSessionAuthentication(SessionAuthentication):
    """Django session cookie + CSRF, accepted only for a tracked, unrevoked web session."""

    def authenticate(self, request: Request) -> tuple[Any, Any] | None:
        tracked = active_web_session(request._request)
        if tracked is None:
            return None
        self.enforce_csrf(request)
        touch(tracked)
        return (tracked.user, tracked)


class StaffSessionScheme(SessionScheme):  # type: ignore[no-untyped-call]
    target_class = "apps.accounts.authentication.StaffSessionAuthentication"
