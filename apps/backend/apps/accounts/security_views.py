"""Password change/reset and session (device) management endpoints (WR-16)."""

from typing import cast

from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.services import record_event

from . import passwords
from .auth_sessions import revoke_all_sessions, revoke_session
from .models import User, UserSession
from .permissions import IsStaffUser, RequiresRecentMFA, staff_session
from .serializers import (
    DetailSerializer,
    PasswordChangeResponseSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    UserSessionSerializer,
)

RESET_ACCEPTED = (
    "Se l'indirizzo appartiene a un account staff attivo, riceverai un'email con le istruzioni."
)
SENSITIVE = method_decorator(
    sensitive_post_parameters("password", "current_password", "new_password", "token"),
    name="dispatch",
)


def _current(request: Request) -> UserSession:
    tracked = staff_session(request)
    assert tracked is not None  # guaranteed by IsStaffUser
    return tracked


@SENSITIVE
class PasswordChangeView(APIView):
    permission_classes = [IsStaffUser, RequiresRecentMFA]
    allow_expired_password = True
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_password"

    @extend_schema(
        operation_id="postAuthPasswordChange",
        request=PasswordChangeSerializer,
        responses={
            200: OpenApiResponse(
                PasswordChangeResponseSerializer, description="Mobile: new token pair."
            ),
            204: OpenApiResponse(description="Web: session kept, other sessions revoked."),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            tokens = passwords.change_password(
                request,
                cast(User, request.user),
                _current(request),
                data["current_password"],
                data["new_password"],
            )
        except passwords.PasswordChangeRejected as error:
            raise ValidationError({error.field: error.messages}, code="invalid") from error
        if tokens is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(tokens)


class PasswordResetRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_password"

    @extend_schema(
        operation_id="postAuthPasswordReset",
        request=PasswordResetRequestSerializer,
        responses={202: DetailSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        passwords.request_reset(request, serializer.validated_data["email"])
        return Response({"detail": RESET_ACCEPTED}, status=status.HTTP_202_ACCEPTED)


@SENSITIVE
class PasswordResetConfirmView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_password"

    @extend_schema(
        operation_id="postAuthPasswordResetConfirm",
        request=PasswordResetConfirmSerializer,
        responses={204: None},
        description="Sets the new password. Does not sign in: MFA is required at next sign-in.",
    )
    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            passwords.confirm_reset(request, data["uid"], data["token"], data["new_password"])
        except passwords.PasswordChangeRejected as error:
            raise ValidationError({error.field: error.messages}, code="invalid") from error
        return Response(status=status.HTTP_204_NO_CONTENT)


class SessionListView(APIView):
    @extend_schema(operation_id="getAuthSessions", responses=UserSessionSerializer(many=True))
    def get(self, request: Request) -> Response:
        sessions = UserSession.objects.filter(
            user=cast(User, request.user), revoked_at__isnull=True
        )
        serializer = UserSessionSerializer(
            sessions, many=True, context={"current": _current(request)}
        )
        return Response(serializer.data)


class SessionRevokeView(APIView):
    @extend_schema(operation_id="deleteAuthSession", request=None, responses={204: None})
    def delete(self, request: Request, pk: int) -> Response:
        tracked = UserSession.objects.filter(
            pk=pk, user=cast(User, request.user), revoked_at__isnull=True
        ).first()
        if tracked is None:
            raise NotFound("Sessione non trovata.")
        revoke_session(tracked, reason="user_revoked")
        record_event("session.revoke", request=request, actor=request.user, target=tracked)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SessionRevokeOthersView(APIView):
    @extend_schema(operation_id="postAuthSessionsRevokeOthers", request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        count = revoke_all_sessions(
            cast(User, request.user), reason="user_revoked_others", keep=_current(request)
        )
        record_event(
            "session.revoke_others",
            request=request,
            actor=request.user,
            target=cast(User, request.user),
            metadata={"revoked_sessions": count},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class SessionRevokeAllView(APIView):
    """Global logout: every web session and every mobile refresh token, this one included."""

    @extend_schema(operation_id="postAuthSessionsRevokeAll", request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        count = revoke_all_sessions(user, reason="global_logout")
        record_event(
            "session.revoke_all",
            request=request,
            actor=user,
            target=user,
            metadata={"revoked_sessions": count},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
