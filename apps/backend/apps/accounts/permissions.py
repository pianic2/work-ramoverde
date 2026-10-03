"""Authorization entry points for staff APIs. Owned by `accounts`.

Other modules must authorize staff endpoints through these classes so that MFA (WR-15),
password policy (WR-16) and role rules (WR-17) are enforced in one place:

- `IsStaffUser`: active staff account authenticated through a tracked, MFA-verified
  `UserSession` (web session or mobile JWT) whose password has not expired (WR-16).
  It is also the DRF default permission.
- `StaffModelPermissions`: `IsStaffUser` + the Django model permission for the action,
  including `view_*` for reads (RBAC roles grant these through groups).
- `RequiresRecentMFA`: add to sensitive actions (step-up authentication).
"""

from datetime import timedelta
from typing import Any, cast

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, DjangoModelPermissions
from rest_framework.request import Request

from .models import User, UserSession


def staff_session(request: Request) -> UserSession | None:
    """The MFA-verified tracked session behind this request, if any."""
    user = request.user
    tracked = getattr(request, "auth", None)
    if not (user and user.is_authenticated and user.is_active and user.is_staff):
        return None
    if not isinstance(tracked, UserSession) or tracked.user_id != user.pk:
        return None
    if not tracked.is_active or tracked.mfa_verified_at is None:
        return None
    return tracked


def is_active_staff(request: Request) -> bool:
    return staff_session(request) is not None


EXPIRED_MESSAGE = "La password è scaduta: cambiala per continuare."


def _enforce_password_age(request: Request, view: Any) -> None:
    """Expired passwords (PASSWORD_MAX_AGE_DAYS) may only reach views that opt in with
    `allow_expired_password = True` (current user, password change, step-up, logout)."""
    expired = cast(User, request.user).password_expired
    if expired and not getattr(view, "allow_expired_password", False):
        raise PermissionDenied(EXPIRED_MESSAGE, code="password_change_required")


class IsStaffUser(BasePermission):
    """Active staff account with an MFA-verified tracked session and a valid password."""

    def has_permission(self, request: Request, view: Any) -> bool:
        if not is_active_staff(request):
            return False
        _enforce_password_age(request, view)
        return True


class StaffModelPermissions(DjangoModelPermissions):
    """Staff account holding the Django model permission for the action, including reads."""

    perms_map: dict[str, list[str]] = {
        **DjangoModelPermissions.perms_map,
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "HEAD": ["%(app_label)s.view_%(model_name)s"],
    }

    def has_permission(self, request: Request, view: Any) -> bool:
        if not is_active_staff(request):
            return False
        _enforce_password_age(request, view)
        return super().has_permission(request, view)


class RequiresRecentMFA(BasePermission):
    """Step-up: the session's last MFA verification must be recent (`STEP_UP_MAX_AGE`)."""

    message = "Conferma la tua identità con il secondo fattore per continuare."
    code = "step_up_required"

    def has_permission(self, request: Request, view: Any) -> bool:
        tracked = staff_session(request)
        if tracked is None or tracked.mfa_verified_at is None:
            return False
        max_age: timedelta = settings.STEP_UP_MAX_AGE
        return timezone.now() - tracked.mfa_verified_at <= max_age
