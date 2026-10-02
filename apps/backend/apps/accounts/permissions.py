"""Authorization entry points for staff APIs. Owned by `accounts` (RBAC, WR-17).

Other modules must authorize staff endpoints through these classes so that
MFA (WR-15) and role rules (WR-17) are enforced in one place.
"""

from typing import Any

from rest_framework.permissions import BasePermission, DjangoModelPermissions
from rest_framework.request import Request
from rest_framework.views import APIView


def is_active_staff(request: Request) -> bool:
    user = request.user
    return bool(user and user.is_authenticated and user.is_active and user.is_staff)


class IsStaffUser(BasePermission):
    """Authenticated, active staff account."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return is_active_staff(request)


class StaffModelPermissions(DjangoModelPermissions):
    """Staff account holding the Django model permission for the action, including reads."""

    perms_map: dict[str, list[str]] = {
        **DjangoModelPermissions.perms_map,
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "HEAD": ["%(app_label)s.view_%(model_name)s"],
    }

    def has_permission(self, request: Request, view: Any) -> bool:
        return is_active_staff(request) and super().has_permission(request, view)
