"""Staff directory, account creation, role assignment and deactivation (WR-17).

Authorization: Django model/custom permissions from the RBAC matrix, plus the
anti-escalation rules in `rbac.check_can_manage`, plus step-up for every change.
"""

from typing import Any, cast

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_event

from . import mfa, rbac
from .auth_sessions import revoke_all_sessions
from .models import User
from .passwords import send_password_link
from .permissions import IsStaffUser, RequiresRecentMFA

ESCALATION_DENIED = "Non puoi assegnare questo ruolo o gestire questo account."
ROLE_CHOICES = [(role.value, rbac.ROLE_LABELS[role]) for role in rbac.Role]


def _has(*perms: str) -> type[BasePermission]:
    class HasPermissions(BasePermission):
        def has_permission(self, request: Request, view: Any) -> bool:
            return all(request.user.has_perm(perm) for perm in perms)

    return HasPermissions


class StaffUserSerializer(serializers.ModelSerializer[User]):
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "role", "is_active", "last_login"]
        read_only_fields = fields

    def get_role(self, obj: User) -> str | None:
        role = rbac.get_role(obj)
        return role.value if role else None


class StaffCreateSerializer(serializers.Serializer[dict[str, Any]]):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, required=False, default="")
    last_name = serializers.CharField(max_length=150, required=False, default="")
    role = serializers.ChoiceField(choices=ROLE_CHOICES)

    def validate_email(self, value: str) -> str:
        value = User.objects.normalize_email(value).lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Esiste già un account con questo indirizzo.")
        return value


class RoleAssignmentSerializer(serializers.Serializer[dict[str, Any]]):
    role = serializers.ChoiceField(choices=ROLE_CHOICES)


class RoleSerializer(serializers.Serializer[dict[str, Any]]):
    code = serializers.ChoiceField(choices=ROLE_CHOICES)
    display_name = serializers.CharField()
    permissions = serializers.ListField(child=serializers.CharField())


def _target(pk: int) -> User:
    user = User.objects.filter(pk=pk, is_staff=True).first()
    if user is None:
        raise NotFound("Account non trovato.")
    return user


def _guard(actor: User, target: User | None, role: rbac.Role | None) -> None:
    try:
        rbac.check_can_manage(actor, target, role)
    except rbac.RoleAssignmentDenied as error:
        raise PermissionDenied(ESCALATION_DENIED, code="role_escalation_denied") from error


class RoleListView(APIView):
    permission_classes = [IsStaffUser, _has("accounts.view_user")]

    @extend_schema(operation_id="getRoles", responses=RoleSerializer(many=True))
    def get(self, request: Request) -> Response:
        rows = [
            {
                "code": role.value,
                "display_name": rbac.ROLE_LABELS[role],
                "permissions": list(perms),
            }
            for role, perms in rbac.ROLE_PERMISSIONS.items()
        ]
        return Response(RoleSerializer(cast(Any, rows), many=True).data)


class StaffUserListView(APIView):
    def get_permissions(self) -> list[BasePermission]:
        if self.request.method == "POST":
            return [
                IsStaffUser(),
                _has("accounts.add_user", "accounts.assign_role")(),
                RequiresRecentMFA(),
            ]
        return [IsStaffUser(), _has("accounts.view_user")()]

    @extend_schema(operation_id="getUsers", responses=StaffUserSerializer(many=True))
    def get(self, request: Request) -> Response:
        users = User.objects.filter(is_staff=True).order_by("email").prefetch_related("groups")
        return Response(StaffUserSerializer(users, many=True).data)

    @extend_schema(
        operation_id="postUsers",
        request=StaffCreateSerializer,
        responses={201: StaffUserSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = StaffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        actor = cast(User, request.user)
        role = rbac.Role(data["role"])
        _guard(actor, None, role)
        with transaction.atomic():
            user = User.objects.create_user(
                email=data["email"],
                password=None,  # unusable: the owner sets it through a single-use link
                first_name=data["first_name"],
                last_name=data["last_name"],
                is_staff=True,
            )
            rbac.set_role(user, role)
        send_password_link(user, invite=True)
        record_event(
            "account.create", request=request, actor=actor, target=user, metadata={"role": role}
        )
        return Response(StaffUserSerializer(user).data, status=status.HTTP_201_CREATED)


class StaffRoleView(APIView):
    permission_classes = [IsStaffUser, _has("accounts.assign_role"), RequiresRecentMFA]

    @extend_schema(
        operation_id="postUserRole", request=RoleAssignmentSerializer, responses=StaffUserSerializer
    )
    def post(self, request: Request, pk: int) -> Response:
        serializer = RoleAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = cast(User, request.user)
        target = _target(pk)
        role = rbac.Role(serializer.validated_data["role"])
        _guard(actor, target, role)
        previous = rbac.get_role(target)
        rbac.set_role(target, role)
        record_event(
            "role.change",
            request=request,
            actor=actor,
            target=target,
            metadata={"from": previous.value if previous else None, "to": role.value},
        )
        return Response(StaffUserSerializer(target).data)


class StaffDeactivateView(APIView):
    permission_classes = [IsStaffUser, _has("accounts.deactivate_user"), RequiresRecentMFA]

    @extend_schema(operation_id="postUserDeactivate", request=None, responses={204: None})
    def post(self, request: Request, pk: int) -> Response:
        actor = cast(User, request.user)
        target = _target(pk)
        _guard(actor, target, None)
        User.objects.filter(pk=target.pk).update(is_active=False)
        revoked = revoke_all_sessions(target, reason="account_deactivated")
        record_event(
            "account.deactivate",
            request=request,
            actor=actor,
            target=target,
            metadata={"revoked_sessions": revoked},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class StaffSecurityResetView(APIView):
    """Incident response / lost device: revoke everything and force a fresh onboarding.

    Revokes all sessions and refresh tokens, removes every second factor and recovery
    code, makes the password unusable and emails a single-use link: the owner must set a
    new password and enroll MFA again before any access.
    """

    permission_classes = [IsStaffUser, _has("accounts.manage_user_security"), RequiresRecentMFA]

    @extend_schema(operation_id="postUserSecurityReset", request=None, responses={204: None})
    def post(self, request: Request, pk: int) -> Response:
        actor = cast(User, request.user)
        target = _target(pk)
        _guard(actor, target, None)
        with transaction.atomic():
            target.set_unusable_password()
            target.save(update_fields=["password", "password_changed_at"])
            mfa.remove_all_factors(target)
        revoked = revoke_all_sessions(target, reason="security_reset")
        send_password_link(target, invite=False)
        record_event(
            "account.security_reset",
            request=request,
            actor=actor,
            target=target,
            metadata={"revoked_sessions": revoked},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
